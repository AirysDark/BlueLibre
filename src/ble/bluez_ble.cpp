#include "ble/ble_backend.h"
#include "ble/bluez_ble.h"
#include <dbus/dbus.h>
#include <cstring>
#include <string>
#include <vector>

static bool call_read_value(DBusConnection* conn, const std::string& char_path, std::vector<uint8_t>& out, std::string& err) {
  DBusMessage* msg = dbus_message_new_method_call("org.bluez", char_path.c_str(), "org.bluez.GattCharacteristic1", "ReadValue");
  if (!msg) { err="dbus_message_new_method_call failed"; return false; }
  DBusMessageIter args, dict;
  dbus_message_iter_init_append(msg, &args);
  dbus_message_iter_open_container(&args, DBUS_TYPE_ARRAY, "{sv}", &dict); // empty options {}
  dbus_message_iter_close_container(&args, &dict);

  DBusError dbus_err; dbus_error_init(&dbus_err);
  DBusMessage* reply = dbus_connection_send_with_reply_and_block(conn, msg, 5000, &dbus_err);
  dbus_message_unref(msg);
  if (!reply) {
    err = dbus_err.message ? dbus_err.message : "ReadValue call failed";
    dbus_error_free(&dbus_err);
    return false;
  }

  DBusMessageIter it;
  if (!dbus_message_iter_init(reply, &it) || dbus_message_iter_get_arg_type(&it) != DBUS_TYPE_ARRAY) {
    err = "Unexpected DBus reply";
    dbus_message_unref(reply);
    return false;
  }
  DBusMessageIter arr;
  dbus_message_iter_recurse(&it, &arr);
  while (dbus_message_iter_get_arg_type(&arr) == DBUS_TYPE_BYTE) {
    uint8_t b; dbus_message_iter_get_basic(&arr, &b);
    out.push_back(b);
    dbus_message_iter_next(&arr);
  }
  dbus_message_unref(reply);
  return true;
}

std::optional<std::vector<uint8_t>>
bluez_read_characteristic(const std::string& char_object_path,
                          std::string* error_out) {
#ifdef PLATFORM_BLUEZ
  DBusError err; dbus_error_init(&err);
  DBusConnection* conn = dbus_bus_get(DBUS_BUS_SYSTEM, &err);
  if (!conn) {
    if (error_out) *error_out = err.message ? err.message : "DBus connect failed";
    dbus_error_free(&err);
    return std::nullopt;
  }
  std::vector<uint8_t> data; std::string e;
  bool ok = call_read_value(conn, char_object_path, data, e);
  if (!ok) { if (error_out) *error_out = e; return std::nullopt; }
  return data;
#else
  (void)char_object_path; (void)error_out;
  return std::nullopt;
#endif
}

std::optional<std::vector<uint8_t>>
ble_read_characteristic(const std::string& device_id_or_path,
                        const std::string& service_uuid,
                        const std::string& characteristic_uuid,
                        std::string* error_out) {
  (void)service_uuid; (void)characteristic_uuid;
#ifdef PLATFORM_BLUEZ
  return bluez_read_characteristic(device_id_or_path, error_out);
#else
  (void)device_id_or_path; (void)error_out;
  return std::nullopt;
#endif
}