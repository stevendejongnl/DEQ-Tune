idf_component_register(
    SRCS "probe_main.c" "deq_usb_device.c" "deq_frame.c"
    INCLUDE_DIRS "."
    REQUIRES nvs_flash esp_timer
)

# deq_usb_device.c counts the host's descriptor reads and records its SETUP
# packets. esp_tinyusb and TinyUSB own those functions, so the linker
# routes each call through a wrapper.
target_link_libraries(${COMPONENT_LIB} INTERFACE
    "-Wl,--wrap=tud_descriptor_device_cb"
    "-Wl,--wrap=tud_descriptor_configuration_cb"
    "-Wl,--wrap=tud_descriptor_string_cb"
    "-Wl,--wrap=dcd_event_handler"
)
