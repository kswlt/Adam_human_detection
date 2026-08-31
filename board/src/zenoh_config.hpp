#pragma once
#include "device_config.hpp"
#include "zenoh-pico.h"

inline void configure_zenoh(z_owned_config_t &cfg, const xt::Json &config, const char *role) {
    const auto &z = config.at("zenoh");
    auto put = [&](uint8_t key, const std::string &value) {
        if (zp_config_insert(z_loan_mut(cfg), key, value.c_str()) != Z_OK)
            throw std::runtime_error("zenoh config insert failed");
    };
    put(Z_CONFIG_MODE_KEY, z.at("mode").get<std::string>());
    const auto &listen = std::string(role)=="camera" ? config.at("camera_zenoh").at("listen") : z.at("listen");
    if (z.at("mode") == "peer" && !listen.empty()) put(Z_CONFIG_LISTEN_KEY, listen[0].get<std::string>());
    if (!z.at("connect").empty()) put(Z_CONFIG_CONNECT_KEY, z.at("connect")[0].get<std::string>());
    put(Z_CONFIG_MULTICAST_SCOUTING_KEY, z.at("scouting").at("multicast").at("enabled").get<bool>() ? "true" : "false");
}
