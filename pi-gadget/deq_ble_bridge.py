#!/usr/bin/env python3
"""Carries the deq-tune REST API over Bluetooth Low Energy.

Why this exists: the car's head unit does wireless Android Auto only, so
projection holds the phone's Wi-Fi all the time. Measured in the car
on 2026-10-09, the phone cannot also hold the Pi's access point: it
reports STA+STA support and even shows both SSIDs at once, but under an
active projection stream the second link collapses to RSSI -127. Moving
the access point to 5 GHz is worse, not better, because the phone
refuses same-band dual STA. The Pi cannot join the car's own network
either. Its BCM43436 radio is 2.4 GHz, and the head unit's access point
is at 5745 MHz. Bluetooth is the remaining option.

BLE rather than SPP/RFCOMM, for two reasons that are not about this car:
a browser cannot open an RFCOMM socket (that ruled Bluetooth out for the
web app), and a smaller board without
Classic Bluetooth can still carry BLE. BLE GATT is the only transport
that serves the native app and a future web frontend.

This is deliberately a *transport*, not a new API. It carries the
existing REST calls to the backend already running on this Pi, so
nothing in the backend, the DTOs, or the car's browse tree changes. If
another board ever relays for the Pi, the framing below can stay as it
is. Only what sits behind `_perform` changes.

Protocol
--------
Two characteristics plus an informational one. A message is JSON, split
across as many chunks as it needs. Each chunk carries one header byte.
Bit 0 set means "last chunk of this message".

    request  (write)   {"id": N, "method": "GET", "path": "/api/...",
                        "body": <optional JSON>}
    response (notify)  {"id": N, "status": 200, "body": <JSON or string>,
                        "body_bytes": <size of body in UTF-8>}

The bridge echoes `id`, so the client can match replies to calls. A request that
never reaches the backend still gets a response, with a status of 0 and
the reason in `body`, because a client waiting forever is worse than a
client told it failed.
"""

import json
import threading
import urllib.error
import urllib.request

import dbus
import dbus.exceptions
import dbus.mainloop.glib
import dbus.service
from gi.repository import GLib

BLUEZ = "org.bluez"
ADAPTER_IFACE = "org.bluez.Adapter1"
GATT_MANAGER_IFACE = "org.bluez.GattManager1"
LE_ADVERTISING_MANAGER_IFACE = "org.bluez.LEAdvertisingManager1"
GATT_SERVICE_IFACE = "org.bluez.GattService1"
GATT_CHRC_IFACE = "org.bluez.GattCharacteristic1"
LE_ADVERTISEMENT_IFACE = "org.bluez.LEAdvertisement1"
DBUS_OM_IFACE = "org.freedesktop.DBus.ObjectManager"
DBUS_PROP_IFACE = "org.freedesktop.DBus.Properties"

BASE = "-7475-4e65-9c21-1f5b6d2a7e01"
SERVICE_UUID = "de900000" + BASE
REQUEST_UUID = "de900001" + BASE
RESPONSE_UUID = "de900002" + BASE
INFO_UUID = "de900003" + BASE

BACKEND = "http://127.0.0.1:8420"
BACKEND_TIMEOUT_SECONDS = 10
LOCAL_NAME = "deq-tune"

# Conservative, and chosen rather than negotiated. BlueZ exposes the
# connection's MTU only once a client subscribes, and getting that wrong
# truncates notifications silently. 180 bytes fits inside the smallest
# MTU any modern phone negotiates, and the payloads here are small JSON:
# the largest real responses are a few kilobytes, so a few
# dozen notifications. Raise it only with a measurement to justify it.
CHUNK_PAYLOAD = 180

# ATT takes 3 bytes of each notification, and this protocol's header takes 1.
ATT_HEADER_BYTES = 3
CHUNK_HEADER_BYTES = 1

LAST_CHUNK = 0x01


def log(message):
    print("deq-ble-bridge: %s" % message, flush=True)


class InvalidArgsException(dbus.exceptions.DBusException):
    _dbus_error_name = "org.freedesktop.DBus.Error.InvalidArgs"


class NotSupportedException(dbus.exceptions.DBusException):
    _dbus_error_name = "org.bluez.Error.NotSupported"


class Application(dbus.service.Object):
    def __init__(self, bus):
        self.path = "/nl/madebysteven/deq"
        self.services = []
        dbus.service.Object.__init__(self, bus, self.path)

    def get_path(self):
        return dbus.ObjectPath(self.path)

    def add_service(self, service):
        self.services.append(service)

    @dbus.service.method(DBUS_OM_IFACE, out_signature="a{oa{sa{sv}}}")
    def GetManagedObjects(self):
        response = {}
        for service in self.services:
            response[service.get_path()] = service.get_properties()
            for chrc in service.characteristics:
                response[chrc.get_path()] = chrc.get_properties()
        return response


class Service(dbus.service.Object):
    def __init__(self, bus, index, uuid, primary=True):
        self.path = "/nl/madebysteven/deq/service%d" % index
        self.bus = bus
        self.uuid = uuid
        self.primary = primary
        self.characteristics = []
        dbus.service.Object.__init__(self, bus, self.path)

    def get_properties(self):
        return {
            GATT_SERVICE_IFACE: {
                "UUID": self.uuid,
                "Primary": self.primary,
                "Characteristics": dbus.Array(
                    [c.get_path() for c in self.characteristics], signature="o"
                ),
            }
        }

    def get_path(self):
        return dbus.ObjectPath(self.path)

    def add_characteristic(self, characteristic):
        self.characteristics.append(characteristic)


class Characteristic(dbus.service.Object):
    def __init__(self, bus, index, uuid, flags, service):
        self.path = service.path + "/char%d" % index
        self.bus = bus
        self.uuid = uuid
        self.flags = flags
        self.service = service
        self.notifying = False
        dbus.service.Object.__init__(self, bus, self.path)

    def get_properties(self):
        properties = {
            "Service": self.service.get_path(),
            "UUID": self.uuid,
            "Flags": self.flags,
        }
        # Only on a characteristic that notifies. A declaration on the
        # others made the whole GATT application malformed. The symptom
        # was a disconnect part way through service discovery, with no
        # error. That looks like a radio problem and hides the schema one.
        if "notify" in self.flags:
            properties["Notifying"] = dbus.Boolean(self.notifying)
        return {GATT_CHRC_IFACE: properties}

    def get_path(self):
        return dbus.ObjectPath(self.path)

    @dbus.service.method(GATT_CHRC_IFACE, in_signature="a{sv}", out_signature="ay")
    def ReadValue(self, options):
        raise NotSupportedException()

    @dbus.service.method(GATT_CHRC_IFACE, in_signature="aya{sv}")
    def WriteValue(self, value, options):
        raise NotSupportedException()

    # Only ResponseCharacteristic declares StartNotify/StopNotify. This
    # class does not. A declaration on both exports the same method twice,
    # and the object's introspection no longer describes a valid
    # characteristic. The symptom is a disconnect during service
    # discovery, with nothing logged on either side.

    @dbus.service.signal(DBUS_PROP_IFACE, signature="sa{sv}as")
    def PropertiesChanged(self, interface, changed, invalidated):
        pass


class ResponseCharacteristic(Characteristic):
    """Notifies the client with reassembled JSON replies, chunk by chunk."""

    def __init__(self, bus, index, service):
        Characteristic.__init__(
            self, bus, index, RESPONSE_UUID, ["notify"], service
        )
        self.chunk_payload = CHUNK_PAYLOAD

    def use_mtu(self, mtu):
        """Fits each chunk inside the MTU that BlueZ reports for the link.

        BlueZ cuts a notification that is longer than the MTU, and it says
        nothing. A cut chunk breaks the reply, and the phone then fails
        with a JSON error. So a smaller MTU makes smaller chunks. A larger
        MTU keeps CHUNK_PAYLOAD.
        """
        fitting = int(mtu) - ATT_HEADER_BYTES - CHUNK_HEADER_BYTES
        self.chunk_payload = max(1, min(CHUNK_PAYLOAD, fitting))

    # This class declares these itself and does not inherit them from
    # Characteristic. dbus-python exports methods per concrete class, and
    # BlueZ's StartNotify did not reach the base class version. The write
    # and the backend call both worked, and the bridge built the reply.
    # Then it dropped the reply, because `notifying` was still False. The
    # bridge logs that case and does not fail silently. That log showed
    # the problem.
    @dbus.service.method(GATT_CHRC_IFACE)
    def StartNotify(self):
        self.notifying = True
        log("client subscribed to replies")

    @dbus.service.method(GATT_CHRC_IFACE)
    def StopNotify(self):
        self.notifying = False
        log("client unsubscribed")

    def send(self, message):
        if not self.notifying:
            log("a reply was ready but nothing is subscribed; dropping it")
            return
        payload = json.dumps(message, separators=(",", ":")).encode("utf-8")
        size = self.chunk_payload
        log("reply %s: %d bytes in %d chunks of %d"
            % (message.get("id"), len(payload), -(-len(payload) // size), size))
        for start in range(0, max(len(payload), 1), size):
            chunk = payload[start:start + size]
            is_last = start + size >= len(payload)
            header = LAST_CHUNK if is_last else 0x00
            self.PropertiesChanged(
                GATT_CHRC_IFACE,
                {"Value": dbus.Array(bytearray([header]) + chunk, signature="y")},
                [],
            )


class RequestCharacteristic(Characteristic):
    """Reassembles chunked requests and runs them against the backend."""

    def __init__(self, bus, index, service, response_characteristic):
        Characteristic.__init__(
            self,
            bus,
            index,
            REQUEST_UUID,
            ["write", "write-without-response"],
            service,
        )
        self.response = response_characteristic
        self.buffer = bytearray()

    @dbus.service.method(GATT_CHRC_IFACE, in_signature="aya{sv}")
    def WriteValue(self, value, options):
        data = bytearray(value)
        if not data:
            return
        if "mtu" in options:
            self.response.use_mtu(options["mtu"])
        header = data[0]
        self.buffer += data[1:]
        if not header & LAST_CHUNK:
            return

        raw = bytes(self.buffer)
        self.buffer = bytearray()
        log("request of %d bytes received" % len(raw))
        try:
            message = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as error:
            log("could not parse a request: %s" % error)
            self.response.send({"id": None, "status": 0, "body": str(error)})
            return

        # The backend call must not run on the main loop: a slow or hung
        # request would stall every other D-Bus method, including the
        # client's next write, and BlueZ would start timing out.
        threading.Thread(
            target=self._perform, args=(message,), daemon=True
        ).start()

    def _perform(self, message):
        request_id = message.get("id")
        reply = {"id": request_id}
        try:
            method = (message.get("method") or "GET").upper()
            path = message.get("path") or "/"
            body = message.get("body")
            data = None
            headers = {"Accept": "application/json"}
            if body is not None:
                data = json.dumps(body).encode("utf-8")
                headers["Content-Type"] = "application/json"

            request = urllib.request.Request(
                BACKEND + path, data=data, headers=headers, method=method
            )
            with urllib.request.urlopen(
                request, timeout=BACKEND_TIMEOUT_SECONDS
            ) as answer:
                reply["status"] = answer.status
                reply["body"] = answer.read().decode("utf-8")
        except urllib.error.HTTPError as error:
            # A 4xx or 5xx is still an answer from the backend, so pass it
            # through rather than reporting it as a transport failure.
            reply["status"] = error.code
            reply["body"] = error.read().decode("utf-8", "replace")
        except Exception as error:
            reply["status"] = 0
            reply["body"] = "%s: %s" % (type(error).__name__, error)

        # The phone compares this with what it reassembled. A lost chunk
        # inside the body still leaves valid JSON, so only the size shows it.
        reply["body_bytes"] = len(reply["body"].encode("utf-8"))

        # Only the main loop's thread can emit notifications. BlueZ's
        # D-Bus connection is not safe to signal from a worker.
        GLib.idle_add(self.response.send, reply)


class InfoCharacteristic(Characteristic):
    """What this bridge is, for a client deciding whether it speaks to it."""

    def __init__(self, bus, index, service):
        Characteristic.__init__(self, bus, index, INFO_UUID, ["read"], service)

    def ReadValue(self, options):
        info = json.dumps(
            {"bridge": "deq-tune", "protocol": 1, "backend": BACKEND},
            separators=(",", ":"),
        )
        return dbus.Array(info.encode("utf-8"), signature="y")


class Advertisement(dbus.service.Object):
    def __init__(self, bus, index):
        self.path = "/nl/madebysteven/deq/advertisement%d" % index
        self.bus = bus
        dbus.service.Object.__init__(self, bus, self.path)

    def get_path(self):
        return dbus.ObjectPath(self.path)

    @dbus.service.method(DBUS_PROP_IFACE, in_signature="s", out_signature="a{sv}")
    def GetAll(self, interface):
        if interface != LE_ADVERTISEMENT_IFACE:
            raise InvalidArgsException()
        return {
            "Type": "peripheral",
            "ServiceUUIDs": dbus.Array([SERVICE_UUID], signature="s"),
            "LocalName": dbus.String(LOCAL_NAME),
            "Includes": dbus.Array(["tx-power"], signature="s"),
        }

    @dbus.service.method(LE_ADVERTISEMENT_IFACE)
    def Release(self):
        pass


def find_adapter(bus):
    manager = dbus.Interface(
        bus.get_object(BLUEZ, "/"), "org.freedesktop.DBus.ObjectManager"
    )
    for path, interfaces in manager.GetManagedObjects().items():
        if GATT_MANAGER_IFACE in interfaces:
            return path
    return None


def main():
    dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
    bus = dbus.SystemBus()

    adapter = find_adapter(bus)
    if adapter is None:
        raise SystemExit("no Bluetooth adapter with a GATT manager")
    log("using adapter %s" % adapter)

    properties = dbus.Interface(
        bus.get_object(BLUEZ, adapter), DBUS_PROP_IFACE
    )
    properties.Set(ADAPTER_IFACE, "Powered", dbus.Boolean(True))

    application = Application(bus)
    service = Service(bus, 0, SERVICE_UUID)
    response = ResponseCharacteristic(bus, 0, service)
    service.add_characteristic(response)
    service.add_characteristic(RequestCharacteristic(bus, 1, service, response))
    service.add_characteristic(InfoCharacteristic(bus, 2, service))
    application.add_service(service)

    gatt_manager = dbus.Interface(
        bus.get_object(BLUEZ, adapter), GATT_MANAGER_IFACE
    )
    advertising_manager = dbus.Interface(
        bus.get_object(BLUEZ, adapter), LE_ADVERTISING_MANAGER_IFACE
    )
    advertisement = Advertisement(bus, 0)

    loop = GLib.MainLoop()

    gatt_manager.RegisterApplication(
        application.get_path(),
        {},
        reply_handler=lambda: log("GATT application registered"),
        error_handler=lambda error: (_ for _ in ()).throw(
            SystemExit("could not register the GATT application: %s" % error)
        ),
    )
    advertising_manager.RegisterAdvertisement(
        advertisement.get_path(),
        {},
        reply_handler=lambda: log("advertising as '%s'" % LOCAL_NAME),
        error_handler=lambda error: (_ for _ in ()).throw(
            SystemExit("could not advertise: %s" % error)
        ),
    )

    log("service %s" % SERVICE_UUID)
    loop.run()


if __name__ == "__main__":
    main()
