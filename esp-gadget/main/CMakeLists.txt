idf_component_register(
    SRCS "probe_main.c" "deq_usb_device.c" "deq_frame.c"
    INCLUDE_DIRS "."
    REQUIRES nvs_flash esp_timer
)
