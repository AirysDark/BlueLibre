#include "models/airpods_models.h"
#include <cstdio>

namespace airpods {

std::string_view ModelName(Model m) {
  switch (m) {
    case Model::AirPods1:    return "AirPods (1st gen)";
    case Model::AirPods2:    return "AirPods (2nd gen)";
    case Model::AirPods3:    return "AirPods (3rd gen)";
    case Model::AirPods4:    return "AirPods 4";
    case Model::AirPods4ANC: return "AirPods 4 (ANC)";
    case Model::AirPodsPro:  return "AirPods Pro";
    case Model::AirPodsPro2: return "AirPods Pro (2nd gen)";
    case Model::AirPodsMax:  return "AirPods Max";
    default:                 return "AirPods (Unknown model)";
  }
}

std::string FallbackName(uint16_t raw_id) {
  char buf[64];
  std::snprintf(buf, sizeof(buf), "AirPods (0x%04X)", raw_id);
  return std::string(buf);
}

} // namespace airpods