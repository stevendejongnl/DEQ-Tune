# Builds the Android accessory gadget function as an out-of-tree module.
#
# Build it on the Pi itself. Its gcc is the same version the running
# kernel was built with, so no cross-compiler and no version mismatch.
#
#     make            build usb_f_accessory.ko
#     make install    install it and run depmod
#     make clean
#
# Every message in this driver is pr_debug, and the Pi's kernel has
# CONFIG_DYNAMIC_DEBUG off, so none of them reach dmesg in a normal build.
# Build with DEBUG=1 to compile them in:
#
#     make DEBUG=1 && make DEBUG=1 install
#
# That is the only way to see which AOA request arrives and when the host
# un-configures the device. Keep the plain build quiet: these messages are
# one line per bulk transfer.
#
# The driver includes <linux/usb/f_accessory.h>, which mainline does not
# have, so `include/` here is put on the include path ahead of the
# kernel's own headers.

obj-m := usb_f_accessory.o
usb_f_accessory-y := f_accessory.o

KERNEL_RELEASE := $(shell uname -r)
KDIR := /lib/modules/$(KERNEL_RELEASE)/build
PWD := $(shell pwd)

ccflags-y := -I$(src)/include

# DEBUG=1 turns this driver's pr_debug calls into real output.
ifeq ($(DEBUG),1)
ccflags-y += -DDEBUG
endif

all:
	$(MAKE) -C $(KDIR) M=$(PWD) modules

install: all
	install -d /lib/modules/$(KERNEL_RELEASE)/extra
	install -m 644 usb_f_accessory.ko /lib/modules/$(KERNEL_RELEASE)/extra/
	depmod -a

clean:
	$(MAKE) -C $(KDIR) M=$(PWD) clean

.PHONY: all install clean
