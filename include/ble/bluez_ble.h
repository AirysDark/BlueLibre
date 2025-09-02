#pragma once
#include <string>
#include <vector>
#include <optional>

std::optional<std::vector<uint8_t>>
bluez_read_characteristic(const std::string& char_object_path,
                          std::string* error_out);