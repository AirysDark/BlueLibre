cmake_minimum_required(VERSION 3.24)
project(AirPodsDesktop VERSION 0.4.0 LANGUAGES CXX)

# Optional in-tree vcpkg for Windows users
if (WIN32 AND NOT DEFINED CMAKE_TOOLCHAIN_FILE AND EXISTS "${CMAKE_SOURCE_DIR}/.vcpkg/scripts/buildsystems/vcpkg.cmake")
  set(CMAKE_TOOLCHAIN_FILE "${CMAKE_SOURCE_DIR}/.vcpkg/scripts/buildsystems/vcpkg.cmake" CACHE STRING "" FORCE)
endif()

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

if (MSVC)
  add_compile_options(/permissive- /Zc:preprocessor /utf-8 /W4 /EHsc)
  add_definitions(-D_WIN32_WINNT=0x0A00) # Windows 10
else()
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

find_package(Threads REQUIRED)

# Platform BLE backends
if (WIN32)
  add_definitions(-DPLATFORM_WINRT)
  set(BLE_BACKEND_SRC src/ble/winrt_ble.cpp)
  set(BLE_BACKEND_INC include/ble/winrt_ble.h)
  set(PLATFORM_LIBS windowsapp)
elseif (UNIX)
  add_definitions(-DPLATFORM_BLUEZ)
  find_package(PkgConfig REQUIRED)
  pkg_check_modules(DBUS REQUIRED dbus-1)
  pkg_check_modules(BLUEZ REQUIRED bluez)
  set(BLE_BACKEND_SRC src/ble/bluez_ble.cpp)
  set(BLE_BACKEND_INC include/ble/bluez_ble.h)
  set(PLATFORM_LIBS ${DBUS_LIBRARIES} ${BLUEZ_LIBRARIES})
  include_directories(${DBUS_INCLUDE_DIRS} ${BLUEZ_INCLUDE_DIRS})
endif()

file(GLOB_RECURSE APP_SOURCES CONFIGURE_DEPENDS
     src/*.cpp src/*.cc src/*.c
     include/*.h include/*.hpp)

add_executable(AirPodsDesktop
  ${APP_SOURCES}
  ${BLE_BACKEND_SRC}
  include/ble/ble_backend.h
  include/models/airpods_models.h
  src/models/airpods_models.cpp
  ${BLE_BACKEND_INC}
)

target_include_directories(AirPodsDesktop PRIVATE include)
target_link_libraries(AirPodsDesktop PRIVATE ${PLATFORM_LIBS} Threads::Threads)

include(GNUInstallDirs)
install(TARGETS AirPodsDesktop RUNTIME DESTINATION ${CMAKE_INSTALL_BINDIR})