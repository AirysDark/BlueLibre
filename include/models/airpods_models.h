#pragma once
#include <cstdint>
#include <string>
#include <string_view>

namespace airpods {

enum class Model : uint16_t {
  Unknown      = 0x0000,
  AirPods1     = 0x2002,
  AirPods2     = 0x2008,
  AirPods3     = 0x2015,
  AirPods4     = 0x2019, // NEW
  AirPods4ANC  = 0x201B, // NEW
  AirPodsPro   = 0x2101,
  AirPodsPro2  = 0x2201,
  AirPodsMax   = 0x2301
};

std::string_view ModelName(Model m);
std::string FallbackName(uint16_t raw_id);

} // namespace airpods