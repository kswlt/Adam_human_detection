#define main radar_service_main
#include "../board/src/xt_radar.cpp"
#undef main
#include <cassert>
#include <random>

static void control_tests() {
    assert((radar_udp_destination()==std::vector<uint8_t>{192,168,0,179,0x07,0x1e}));
    const char *old_source=BOARD_IP;
    BOARD_IP="192.168.0.250";
    assert((radar_udp_destination()==std::vector<uint8_t>{192,168,0,250,0x07,0x1e}));
    BOARD_IP=old_source;
    std::ostringstream row;
    row << "eth0 " << std::hex << inet_addr(RADAR_IP) << " 00000000 0005 0 0 0 FFFFFFFF 0 0 0\n";
    std::istringstream correct(row.str());
    assert(radar_route_present(correct));
    for (auto line : {"eth0 00000000 C801A8C0 0003 0 0 0 00000000", "eth1 6500A8C0 0 5 0 0 0 FFFFFFFF", "truncated"}) {
        std::istringstream wrong(line);
        assert(!radar_route_present(wrong));
    }
    std::vector<uint8_t> data;
    uint8_t status=0xff;
    const uint8_t v3[]={18,42,0,3,3}, v2[]={18,42,0x30,2}, rejected[]={1,3,3,3}, invalid[]={1,0,9};
    assert(decode_radar_response(v3,sizeof v3,data,status) && status==0 && data==std::vector<uint8_t>{42});
    assert(decode_radar_response(v2,sizeof v2,data,status) && status==0 && data==std::vector<uint8_t>{42});
    assert(decode_radar_response(rejected,sizeof rejected,data,status) && status==3 && data.empty());
    assert(!decode_radar_response(invalid,sizeof invalid,data,status));
    assert(!decode_radar_response(v3,2,data,status));
    int pair[2];
    assert(socketpair(AF_UNIX,SOCK_STREAM,0,pair)==0);
    g_tcpfd=pair[0];
    const uint8_t event[]={0x7e,0xff,0xaa,0x55,5,0,0,0,157,12,7,3,3,0xff,0x7e,0x55,0xaa};
    assert(send(pair[1],event,6,0)==6);
    drain_control_events(); assert(g_control_rx.size()==6);
    assert(send(pair[1],event+6,sizeof event-6,0)==sizeof event-6);
    drain_control_events(); assert(g_control_rx.empty() && g_tcpfd>=0);
    close(pair[1]); drain_control_events(); assert(g_tcpfd==-1);
}
static void publish_queue_tests() {
    PublishQueue<unsigned, 3> queue;
    unsigned item=0;
    assert(!queue.pop(item,std::chrono::milliseconds(1)));
    // Simulate a blocked publisher: acquisition still progresses with bounded memory.
    for (unsigned n=0;n<10000;++n) queue.push(n);
    const auto stats=queue.stats();
    assert(stats.first==3 && stats.second==9997);
    for (unsigned n=9997;n<10000;++n) assert(queue.pop(item) && item==n);
    std::thread consumer([&]{ assert(queue.pop(item,std::chrono::seconds(1)) && item==42); });
    queue.push(42); consumer.join();
    assert(queue.stats().first==0);
}
static void request_tests() {
    std::array<int32_t,6> v{};
    assert(xt::parse_request(nullptr,0,v));
    for (auto bad : std::vector<std::vector<uint8_t>>{{0x80},{0},{0x0a,5,1},{0x12,0},
            {0x18,0xff,0xff,0xff,0xff,0x1f},{0x0a,2,0x08,0x80},
            {0x80,0x80,0x80,0x80,0x80,0x80,0x80,0x80,0x80,2}})
        assert(!xt::parse_request(bad.data(),bad.size(),v));
    const uint8_t good[]={0x0a,2,0x08,1,0x18,8,0x20,20,0x28,4};
    assert(xt::parse_request(good,sizeof good,v) && v[1]==4 && v[2]==10 && v[3]==2);
    std::mt19937 rng(42);
    for (int n=0; n<10000; ++n) {
        std::vector<uint8_t> bytes(rng()%512);
        for (auto &b:bytes) b=uint8_t(rng());
        xt::parse_request(bytes.data(),bytes.size(),v);
    }
}
static void config_tests() {
    char tmp[]="/tmp/xt-config-unit-XXXXXX";
    assert(mkdtemp(tmp));
    auto path=std::string(tmp)+"/config.json";
    setenv("XT_CONFIG_FILE",path.c_str(),1);
    auto cfg=xt::load_config(true);
    assert(cfg["sensors"]["image_fps"]==10);
    cfg["sensors"]["lidar_fps"]=4;
    cfg["additional"]={{"preserve",true}};
    cfg["radar_network"]={{"interface","eth1"},{"source_address","192.168.0.250"}};
    xt::save_config(cfg);
    assert(xt::load_config()==cfg);
    for (const char *bad : {"0.0.0.0","127.0.0.1","224.1.2.3","999.1.2.3","not-an-ip"}) {
        auto invalid=cfg;
        invalid["radar_network"]["source_address"]=bad;
        bool rejected=false;
        try { xt::validate(invalid); } catch (...) { rejected=true; }
        assert(rejected);
    }
    auto invalid=cfg; invalid["radar_network"]["interface"]="eth1;reboot";
    bool rejected=false;
    try { xt::validate(invalid); } catch (...) { rejected=true; }
    assert(rejected);
    auto before=xt::read_file(path);
    cfg["sensors"]["image_format"]=3;
    bool failed=false;
    try { xt::save_config(cfg); } catch (...) { failed=true; }
    assert(failed && before==xt::read_file(path));
    failed=false;
    try { xt::atomic_write(std::string(tmp)+"/missing/config.json","bad"); } catch (...) { failed=true; }
    assert(failed && before==xt::read_file(path));
    xt::atomic_write(path,"{broken");
    failed=false;
    try { xt::load_config(true); } catch (...) { failed=true; }
    assert(failed && xt::read_file(path)=="{broken");
    unlink(path.c_str()); unlink((path+".lock").c_str()); rmdir(tmp);
}
static void frame_tests() {
    std::vector<uint8_t> packet(40),out,imu;
    bool frame=false,is_imu=false;
    auto put16=[&](size_t off,uint16_t v){memcpy(packet.data()+off,&v,2);};
    auto put32=[&](size_t off,uint32_t v){memcpy(packet.data()+off,&v,4);};
    const uint8_t payload[]={0x7e,0xff,0xaa,0x55,0,0,0,0,251,0,0,0,0,0,0,0,0xff,0x7e,0x55,0xaa};
    put16(0,1); put32(2,sizeof payload); put16(6,10); put32(8,0);
    memcpy(packet.data()+20,payload,10);
    assemble_udp(packet.data(),30,out,frame,is_imu,imu); assert(!frame);
    assemble_udp(packet.data(),30,out,frame,is_imu,imu); assert(!frame && g_frames[0].count==10);
    put32(8,10); memcpy(packet.data()+20,payload+10,10);
    assemble_udp(packet.data(),30,out,frame,is_imu,imu); assert(frame && out.size()==8);
    put32(2,0xffffffff); assemble_udp(packet.data(),30,out,frame,is_imu,imu); assert(!frame);
    put16(6,8); assemble_udp(packet.data(),28,out,frame,is_imu,imu); assert(!is_imu);
    FrameInfo info{}; info.magicToken=0x33CCAA50; info.imageflags=3; info.unit_div=1;
    info.infosize=sizeof info; info.timestamp[0]=12345;
    std::vector<uint8_t> bytes(20+sizeof info,0);
    bytes[0]=251; bytes[4]=bytes[6]=1; bytes[16]=1; bytes[18]=2;
    memcpy(bytes.data()+20,&info,sizeof info);
    uint16_t w,h; uint64_t sec; uint32_t ns; FrameInfo parsed;
    std::vector<uint32_t> dist; std::vector<uint16_t> amp;
    assert(parse_frame(bytes,w,h,dist,amp,sec,ns,parsed) && dist[0]==1 && amp[0]==2);
    bytes[bytes.size()-4]=100;
    assert(!parse_frame(bytes,w,h,dist,amp,sec,ns,parsed));
    std::mt19937 rng(44);
    for (int n=0;n<10000;++n) {
        bytes.resize(rng()%1500);
        for (auto &b:bytes) b=uint8_t(rng());
        parse_frame(bytes,w,h,dist,amp,sec,ns,parsed);
        assemble_udp(bytes.data(),bytes.size(),out,frame,is_imu,imu);
    }
}
int main() {
    control_tests(); publish_queue_tests(); request_tests(); config_tests(); frame_tests();
    printf("PASS: config atomic persistence, malformed protobuf, 20000 fuzz cases, UDP duplicates/bounds, FrameInfo bounds (%zu)\n",sizeof(FrameInfo));
}
