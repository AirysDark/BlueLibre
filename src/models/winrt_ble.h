#include "ble/ble_backend.h"
#include "ble/winrt_ble.h"
#include <winrt/Windows.Devices.Bluetooth.h>
#include <winrt/Windows.Devices.Bluetooth.GenericAttributeProfile.h>
#include <winrt/Windows.Devices.Enumeration.h>
#include <winrt/Windows.Storage.Streams.h>
#include <codecvt>
#include <locale>

using namespace winrt;
using namespace Windows::Devices::Bluetooth;
using namespace Windows::Devices::Bluetooth::GenericAttributeProfile;
using namespace Windows::Devices::Enumeration;
using namespace Windows::Storage::Streams;

static std::wstring widen(const std::string& s) {
  std::wstring_convert<std::codecvt_utf8_utf16<wchar_t>> conv;
  return conv.from_bytes(s);
}
static std::string narrow(const std::wstring& ws) {
  std::wstring_convert<std::codecvt_utf8_utf16<wchar_t>> conv;
  return conv.to_bytes(ws);
}

std::optional<std::vector<uint8_t>>
winrt_read_characteristic(const std::wstring& device_id_w,
                          const std::wstring& service_uuid_w,
                          const std::wstring& char_uuid_w,
                          std::wstring* error_out) {
#ifdef PLATFORM_WINRT
  try {
    init_apartment(apartment_type::multi_threaded);
    auto dev = BluetoothLEDevice::FromIdAsync(hstring{device_id_w}).get();
    if (!dev) { if (error_out) *error_out=L"BluetoothLEDevice null"; return std::nullopt; }
    auto svcRes = dev.GetGattServicesForUuid(guid{service_uuid_w});
    if (svcRes.Status()!=GattCommunicationStatus::Success || svcRes.Services().Size()==0) {
      if (error_out) *error_out=L"Service not found"; return std::nullopt;
    }
    auto svc = svcRes.Services().GetAt(0);
    auto chRes = svc.GetCharacteristicsForUuid(guid{char_uuid_w});
    if (chRes.Status()!=GattCommunicationStatus::Success || chRes.Characteristics().Size()==0) {
      if (error_out) *error_out=L"Characteristic not found"; return std::nullopt;
    }
    auto ch = chRes.Characteristics().GetAt(0);
    auto read = ch.ReadValueAsync().get();
    if (read.Status()!=GattCommunicationStatus::Success) {
      if (error_out) *error_out=L"Read failed"; return std::nullopt;
    }
    auto buffer = read.Value();
    DataReader reader = DataReader::FromBuffer(buffer);
    std::vector<uint8_t> out(reader.UnconsumedBufferLength());
    reader.ReadBytes(out);
    return out;
  } catch (const hresult_error& ex) {
    if (error_out) *error_out = ex.message();
    return std::nullopt;
  } catch (...) {
    if (error_out) *error_out = L"Unknown exception";
    return std::nullopt;
  }
#else
  (void)device_id_w; (void)service_uuid_w; (void)char_uuid_w; (void)error_out;
  return std::nullopt;
#endif
}

std::optional<std::vector<uint8_t>>
ble_read_characteristic(const std::string& device_id,
                        const std::string& service_uuid,
                        const std::string& characteristic_uuid,
                        std::string* error_out) {
#ifdef PLATFORM_WINRT
  std::wstring err;
  auto res = winrt_read_characteristic(widen(device_id), widen(service_uuid), widen(characteristic_uuid), &err);
  if (!res && error_out) *error_out = narrow(err);
  return res;
#else
  (void)device_id; (void)service_uuid; (void)characteristic_uuid; (void)error_out;
  return std::nullopt;
#endif
}