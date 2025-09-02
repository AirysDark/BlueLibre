#pragma once
#include <string>
#include <vector>
#include <optional>

// Unified GATT read for both Windows & Linux backends.
std::optional<std::vector<uint8_t>>
ble_read_characteristic(const std::string& device_id,
                        const std::string& service_uuid,
                        const std::string& characteristic_uuid,
                        std::string* error_out = nullptr);