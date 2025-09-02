#pragma once
#include <string>
#include <vector>
#include <optional>

std::optional<std::vector<uint8_t>>
winrt_read_characteristic(const std::wstring& device_id_w,
                          const std::wstring& service_uuid_w,
                          const std::wstring& char_uuid_w,
                          std::wstring* error_out);