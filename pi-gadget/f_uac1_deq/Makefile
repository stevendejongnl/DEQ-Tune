# Builds the UAC1 gadget function, adapted for the Pioneer DEQ, as an
# out-of-tree module.
#
# Build it on the Pi itself. Its gcc is the same version the running
# kernel was built with, so no cross-compiler and no version mismatch.
#
#     make            build usb_f_uac1_deq.ko
#     make install    install it and run depmod
#     make clean
#
# The module registers the configfs function type "uac1deq", not "uac1",
# so it loads beside the in-tree usb_f_uac1 and does not replace it. To
# go back to the stock driver, change AUDIO_FUNCTION_TYPE in
# deq_accessory.py and reboot. Nothing has to be uninstalled.
#
# This driver calls into u_audio, which the kernel ships as its own
# module. Every symbol it needs is EXPORT_SYMBOL_GPL, so no in-tree
# source is required to link against it -- only the headers below.
#
# u_uac1.h, u_audio.h and uac_common.h are private kernel headers that
# linux-headers does not install, so this directory carries its own
# copies and `make` finds them beside the source. README.md says which
# kernel they came from. They must match the running kernel: u_audio.h
# describes a struct this module passes to the kernel's own u_audio, so a
# copy from a different version would disagree about its layout.

obj-m := usb_f_uac1_deq.o
usb_f_uac1_deq-y := f_uac1_deq.o

KERNEL_RELEASE := $(shell uname -r)
KDIR := /lib/modules/$(KERNEL_RELEASE)/build
PWD := $(shell pwd)

all:
	$(MAKE) -C $(KDIR) M=$(PWD) modules

install: all
	install -d /lib/modules/$(KERNEL_RELEASE)/extra
	install -m 644 usb_f_uac1_deq.ko /lib/modules/$(KERNEL_RELEASE)/extra/
	depmod -a

clean:
	$(MAKE) -C $(KDIR) M=$(PWD) clean

.PHONY: all install clean
