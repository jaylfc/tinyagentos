#!/bin/bash

# TinyAgentOS Armbian build extension
# Hooks into the Armbian build process to customise the image.

function extension_prepare_config__tinyagentos() {
    display_alert "TinyAgentOS" "Configuring build" "info"
    EXTRA_IMAGE_SUFFIXES+=("-tinyagentos")
}

function post_customize_image__tinyagentos() {
    display_alert "TinyAgentOS" "Post-customization" "info"
    # Verify critical paths exist in the image
    [[ -d "${SDCARD}/opt/tinyagentos" ]] || \
        display_alert "TinyAgentOS" "/opt/tinyagentos missing — customize-image.sh may have failed" "warn"
}
