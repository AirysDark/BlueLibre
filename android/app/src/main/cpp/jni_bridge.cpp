#include <jni.h>
#include <string>
#include <cstdio>

static const char* NameForModel(uint16_t id) {
  switch (id) {
    case 0x2002: return "AirPods (1st gen)";
    case 0x2008: return "AirPods (2nd gen)";
    case 0x2015: return "AirPods (3rd gen)";
    case 0x2019: return "AirPods 4";
    case 0x201B: return "AirPods 4 (ANC)";
    case 0x2101: return "AirPods Pro";
    case 0x2201: return "AirPods Pro (2nd gen)";
    case 0x2301: return "AirPods Max";
    default:     return nullptr;
  }
}

static std::string FallbackName(uint16_t id) {
  char buf[64];
  std::snprintf(buf, sizeof(buf), "AirPods (0x%04X)", id);
  return std::string(buf);
}

extern "C" JNIEXPORT jstring JNICALL
Java_com_yourco_airpods_NativeBridge_parseAirPodsPayload(
    JNIEnv* env, jobject, jbyteArray payload) {
  const jsize n = env->GetArrayLength(payload);
  if (n < 2) return env->NewStringUTF("AirPods (Unknown model)");
  std::string buf(n, '\0');
  env->GetByteArrayRegion(payload, 0, n, reinterpret_cast<jbyte*>(&buf[0]));
  uint16_t model_id = static_cast<uint8_t>(buf[0]) | (static_cast<uint16_t>(static_cast<uint8_t>(buf[1]))<<8);
  if (const char* known = NameForModel(model_id)) return env->NewStringUTF(known);
  std::string pretty = FallbackName(model_id);
  return env->NewStringUTF(pretty.c_str());
}
