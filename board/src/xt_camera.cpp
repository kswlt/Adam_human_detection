/******************************************************************************
 * xt_camera.cpp - MC800S native JPEG snapshot -> Space Camera Protocol V1.0
 *
 * Data channel:
 *   active/{sn}/image  ImageMsgArray  10Hz  format=JPEG(2)
 *
 * Payload:
 *   ImageMsgArray.array has exactly one ImageMsg.
 *   ImageMsg.format = ImageFormatJpeg(2)
 *   ImageMsg.width/height = dimensions parsed from actual JPEG bytes
 *   ImageMsg.data = complete JPEG file bytes, unmodified
 ******************************************************************************/
#include <atomic>
#include <chrono>
#include <condition_variable>
#include <csignal>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <ctime>
#include <deque>
#include <fstream>
#include <mutex>
#include <string>
#include <thread>
#include <vector>

#include <arpa/inet.h>
#include <dirent.h>
#include <errno.h>
#include <fcntl.h>
#include <netinet/in.h>
#include <sys/select.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <unistd.h>

#include "zenoh-pico.h"
#include "zenoh_config.hpp"
#include "snapshot_client.hpp"

static const char *CAMERA_IP = "192.168.0.123";
static const int CAMERA_PORT = 80;
static const char *CAM_USER = "admin";
static const char *CAM_PASS_MD5 = "E10ADC3949BA59ABBE56E057F20F883E";
static const int DEFAULT_SNAPSHOT_STREAM = 1; // MC800S: 1=1920x1080, 0=720x480
static const int IMAGE_FORMAT_JPEG = 2;
static int TARGET_HZ = 10;
static const char *SN_FILE = "/mnt/system/factory-data/Lixel.yaml";
static std::string g_sn = "LX2601F10001";
static const char *RAW_DIR = "/userdata/xtapp/raw_camera";
static const int RAW_WINDOW_SEC = 300;
static const int RAW_SHARD_SEC = 60;

static z_owned_publisher_t g_pub_img;
static std::atomic<bool> g_running{true};
static std::atomic<uint32_t> g_seq{0};

struct Frame {
    std::vector<uint8_t> jpeg;
    uint32_t width = 0;
    uint32_t height = 0;
    int64_t stamp_ns = 0;
    uint64_t capture_id = 0;
    int64_t fetched_ns = 0;
    double http_ms = 0;
};

static std::mutex g_q_mtx;
static std::condition_variable g_q_cv;
static std::deque<Frame> g_queue;
static const size_t QUEUE_MAX = 3;

static FILE *g_rawfile = NULL;
static char g_rawpath[512] = {0};
static time_t g_rawshard = 0;
static bool g_raw_enabled = false;

static int snapshot_stream() {
    const char *v = getenv("XT_CAMERA_SNAPSHOT_STREAM");
    if (!v || !*v) return DEFAULT_SNAPSHOT_STREAM;
    int s = atoi(v);
    return s == 0 ? 0 : 1;
}

static bool env_enabled(const char *name) {
    const char *v = getenv(name);
    return v && (*v == '1' || *v == 'y' || *v == 'Y' || *v == 't' || *v == 'T');
}

static int64_t monotonic_ns() {
    return std::chrono::duration_cast<std::chrono::nanoseconds>(
        std::chrono::steady_clock::now().time_since_epoch()).count();
}

static void load_sn() {
    std::ifstream f(SN_FILE);
    if (f.good()) {
        std::string line;
        while (std::getline(f, line)) {
            auto pos = line.find("device_sn");
            if (pos == std::string::npos) continue;
            auto c = line.find(':');
            if (c == std::string::npos) continue;
            std::string v = line.substr(c + 1);
            size_t a = v.find_first_not_of(" \t\r\n\"");
            size_t b = v.find_last_not_of(" \t\r\n\"");
            if (a != std::string::npos) g_sn = v.substr(a, b - a + 1);
        }
    }
    printf("[cfg] device_sn=%s\n", g_sn.c_str());
}

static void raw_mkdir(void) { mkdir(RAW_DIR, 0777); }

static void raw_cleanup(time_t now) {
    time_t cutoff = now - RAW_WINDOW_SEC - 60;
    DIR *d = opendir(RAW_DIR);
    if (!d) return;
    struct dirent *e;
    while ((e = readdir(d)) != NULL) {
        if (strncmp(e->d_name, "raw-", 4) != 0) continue;
        char fp[700];
        snprintf(fp, sizeof fp, "%s/%s", RAW_DIR, e->d_name);
        struct stat st;
        if (stat(fp, &st) == 0 && st.st_mtime < cutoff) remove(fp);
    }
    closedir(d);
}

static void raw_open_shard(time_t now) {
    if (g_rawfile && now >= g_rawshard && now < g_rawshard + RAW_SHARD_SEC) return;
    if (g_rawfile) { fclose(g_rawfile); g_rawfile = NULL; }
    struct tm tmv;
    localtime_r(&now, &tmv);
    char name[64];
    strftime(name, sizeof name, "raw-%Y%m%d-%H%M%S.bin", &tmv);
    snprintf(g_rawpath, sizeof g_rawpath, "%s/%s", RAW_DIR, name);
    g_rawfile = fopen(g_rawpath, "ab");
    g_rawshard = now;
    printf("[raw] new shard: %s\n", g_rawpath);
}

static size_t raw_append(int64_t ts_ns, const uint8_t *data, size_t len) {
    static uint32_t flush_count = 0;
    if (!g_raw_enabled) return 0;
    raw_mkdir();
    time_t now = time(NULL);
    raw_cleanup(now);
    raw_open_shard(now);
    if (!g_rawfile) return 0;
    uint8_t hdr[12];
    memcpy(hdr, &ts_ns, 8);
    uint32_t l = (uint32_t)len;
    memcpy(hdr + 8, &l, 4);
    fwrite(hdr, 1, 12, g_rawfile);
    size_t w = fwrite(data, 1, len, g_rawfile);
    if ((++flush_count % 10) == 0) fflush(g_rawfile);
    return 12 + w;
}

class PBWriter {
public:
    std::vector<uint8_t> buf;
    void varint(uint64_t v) {
        while (v >= 0x80) { buf.push_back((uint8_t)(v & 0x7f) | 0x80); v >>= 7; }
        buf.push_back((uint8_t)v);
    }
    void tag(int field, int wire) { varint(((uint64_t)field << 3) | (uint64_t)wire); }
    void u32(int field, uint32_t v) { tag(field, 0); varint(v); }
    void s64(int field, int64_t v) { tag(field, 0); varint(zigzag(v)); }
    void len(int field, const uint8_t *p, size_t n) { tag(field, 2); varint(n); buf.insert(buf.end(), p, p + n); }
    static uint64_t zigzag(int64_t v) { return (uint64_t(v) << 1) ^ uint64_t(-(v < 0)); }
};

static std::vector<uint8_t> build_image_array_msg(const Frame &f, uint32_t seq) {
    PBWriter arr;
    PBWriter m;
    PBWriter h;
    h.u32(1, seq);
    h.s64(2, f.stamp_ns);
    h.s64(3, 0);
    m.len(1, h.buf.data(), h.buf.size());
    m.u32(2, IMAGE_FORMAT_JPEG);
    m.u32(3, f.width);
    m.u32(4, f.height);
    m.len(5, f.jpeg.data(), f.jpeg.size());
    arr.len(1, m.buf.data(), m.buf.size());
    return arr.buf;
}

static bool parse_jpeg_size(const std::vector<uint8_t> &jpeg, uint32_t &w, uint32_t &h) {
    if (jpeg.size() < 4 || jpeg[0] != 0xff || jpeg[1] != 0xd8) return false;
    size_t i = 2;
    while (i + 9 < jpeg.size()) {
        if (jpeg[i] != 0xff) { i++; continue; }
        while (i < jpeg.size() && jpeg[i] == 0xff) i++;
        if (i >= jpeg.size()) return false;
        uint8_t marker = jpeg[i++];
        if (marker == 0xd9 || marker == 0xda) return false;
        if (marker == 0x01 || (marker >= 0xd0 && marker <= 0xd7)) continue;
        if (i + 2 > jpeg.size()) return false;
        uint16_t seg_len = ((uint16_t)jpeg[i] << 8) | jpeg[i + 1];
        if (seg_len < 2 || i + seg_len > jpeg.size()) return false;
        if ((marker >= 0xc0 && marker <= 0xc3) || (marker >= 0xc5 && marker <= 0xc7) ||
            (marker >= 0xc9 && marker <= 0xcb) || (marker >= 0xcd && marker <= 0xcf)) {
            if (seg_len < 7) return false;
            h = ((uint16_t)jpeg[i + 3] << 8) | jpeg[i + 4];
            w = ((uint16_t)jpeg[i + 5] << 8) | jpeg[i + 6];
            return w > 0 && h > 0;
        }
        i += seg_len;
    }
    return false;
}


static void push_frame(Frame &&f) {
    std::lock_guard<std::mutex> lk(g_q_mtx);
    while (g_queue.size() >= QUEUE_MAX) g_queue.pop_front();
    g_queue.push_back(std::move(f));
    g_q_cv.notify_one();
}

static void capture_thread_main() {
    int stream = snapshot_stream();
    printf("[cap] snapshot stream=%d target=%dHz\n", stream, TARGET_HZ);
    std::string url = std::string("http://") + CAMERA_IP + ":" + std::to_string(CAMERA_PORT) +
        "/cgi-bin/snapshot.cgi?stream=" + std::to_string(stream) + "&username=" + CAM_USER + "&password=" + CAM_PASS_MD5;
    HttpSnapshotClient cli(url);
    uint64_t captures = 0, fails = 0;
    double http_sum=0, http_max=0, first_sum=0;
    uint64_t new_connections=0;
    auto period = std::chrono::nanoseconds(1000000000 / TARGET_HZ);
    auto next = std::chrono::steady_clock::now();

    while (g_running.load()) {
        next += period;
        std::vector<uint8_t> jpeg;
        uint32_t w = 0, h = 0;
        int64_t ts = monotonic_ns();
        const bool success = cli.get(jpeg) && parse_jpeg_size(jpeg, w, h);
        if (success) {
            Frame f;
            f.jpeg = std::move(jpeg);
            f.width = w;
            f.height = h;
            f.stamp_ns = ts;
            f.capture_id = ++captures;
            f.fetched_ns = monotonic_ns();
            f.http_ms = cli.total_ms;
            push_frame(std::move(f));
        } else {
            fails++;
            if (fails <= 5 || fails % 20 == 0)
                printf("[cap] request failed curl=%d status=%ld http_ms=%.1f\n", int(cli.result), cli.status, cli.total_ms);
        }
        http_sum += cli.total_ms;
        first_sum += cli.first_byte_ms;
        http_max = std::max(http_max, cli.total_ms);
        new_connections += cli.connections;
        if (((captures + fails) % 100) == 0) {
            std::lock_guard<std::mutex> lk(g_q_mtx);
            printf("[cap] ok=%llu fail=%llu queue=%zu http_avg_ms=%.2f first_avg_ms=%.2f http_max_ms=%.2f connects=%llu/100\n",
                   (unsigned long long)captures, (unsigned long long)fails, g_queue.size(),
                   http_sum/100, first_sum/100, http_max, (unsigned long long)new_connections);
            http_sum=http_max=first_sum=0; new_connections=0;
        }
        // Do not accumulate catch-up debt or replay queued old frames after an outage.
        auto now = std::chrono::steady_clock::now();
        if (next < now) next = now;
        if (!success) next = now + std::chrono::milliseconds(50);
        std::this_thread::sleep_until(next);
    }
}

static bool pop_frame(Frame &f) {
    std::unique_lock<std::mutex> lk(g_q_mtx);
    g_q_cv.wait(lk, [] { return !g_queue.empty() || !g_running.load(); });
    if (g_queue.empty()) return false;
    f = std::move(g_queue.front());
    g_queue.pop_front();
    return true;
}

int main() {
    signal(SIGPIPE, SIG_IGN);
    setvbuf(stdout, NULL, _IONBF, 0);
    xt::Json settings;
    try { settings = xt::load_config(true); TARGET_HZ = settings["sensors"]["image_fps"].get<int>(); }
    catch (const std::exception &e) { fprintf(stderr, "[cfg] %s\n", e.what()); return 1; }
    if (curl_global_init(CURL_GLOBAL_DEFAULT) != CURLE_OK) return 1;
    printf("[cam] MC800S native JPEG snapshot -> protocol image channel\n");
    g_raw_enabled = env_enabled("XT_CAMERA_RAW");
    printf("[cam] raw record %s dir=%s/ window=%ds\n", g_raw_enabled ? "on" : "off", RAW_DIR, RAW_WINDOW_SEC);
    load_sn();
    if (g_raw_enabled) {
        raw_mkdir();
        raw_cleanup(time(NULL));
    }

    z_owned_session_t s;
    int r = -1;
    while (r != Z_OK) {
        z_owned_config_t cfg;
        z_config_default(&cfg);
        configure_zenoh(cfg, settings, "camera");
        r = z_open(&s, z_move(cfg), NULL);
        if (r != Z_OK) {
            printf("[cam] zenoh z_open ret=%d, retry in 5s\n", r);
            sleep(5);
        }
    }
    printf("[cam] zenoh z_open OK\n");
    int read_result = zp_start_read_task(z_loan_mut(s), NULL);
    int lease_result = zp_start_lease_task(z_loan_mut(s), NULL);
    printf("[cam] zenoh read_task ret=%d lease_task ret=%d\n",
           read_result, lease_result);
    if (read_result != Z_OK || lease_result != Z_OK) return 1;

    char key[128];
    snprintf(key, sizeof key, "active/%s/image", g_sn.c_str());
    z_owned_keyexpr_t ke;
    z_keyexpr_from_str(&ke, key);
    if (z_declare_publisher(z_loan(s), &g_pub_img, z_loan(ke), NULL) != Z_OK) {
        printf("[cam] publisher declare failed\n");
        return 1;
    }
    printf("[cam] publisher %s ready\n", key);

    std::thread cap(capture_thread_main);
    uint64_t published = 0, dropped = 0, put_failures = 0;
    uint64_t last_capture_id = 0;

    while (true) {
        Frame f;
        if (!pop_frame(f)) continue;
        if (last_capture_id && f.capture_id > last_capture_id + 1) dropped += f.capture_id - last_capture_id - 1;
        last_capture_id = f.capture_id;
        double queue_ms = (monotonic_ns() - f.fetched_ns) / 1e6;
        if (queue_ms > 300) { ++dropped; continue; }
        size_t rw = raw_append(f.stamp_ns, f.jpeg.data(), f.jpeg.size());

        uint32_t seq = g_seq++;
        auto encode_start = monotonic_ns();
        auto msg = build_image_array_msg(f, seq);
        z_owned_bytes_t payload;
        z_bytes_copy_from_buf(&payload, msg.data(), msg.size());
        double pb_ms = (monotonic_ns() - encode_start)/1e6;
        auto put_start = monotonic_ns();
        int pr = z_publisher_put(z_loan(g_pub_img), z_move(payload), NULL);
        double put_ms = (monotonic_ns() - put_start)/1e6;
        if (pr != Z_OK) ++put_failures;
        published++;
        if ((published % 100) == 0 || pr != Z_OK || put_ms > 100 || f.http_ms > 200) {
            printf("[cam] seq=%u pub=%llu jpeg=%zuB %ux%u msg=%zuB put=%d dropped=%llu raw%zuB http_ms=%.2f queue_ms=%.2f pb_ms=%.2f put_ms=%.2f put_fail=%llu\n",
                   seq, (unsigned long long)published, f.jpeg.size(), f.width, f.height,
                   msg.size(), pr, (unsigned long long)dropped, rw, f.http_ms, queue_ms, pb_ms, put_ms,
                   (unsigned long long)put_failures);
        }
    }

    g_running = false;
    g_q_cv.notify_all();
    cap.join();
    return 0;
}
