// firmware/bw16/main/packet_format.h
// Binary packet wire format — locked (see CLAUDE.md §8)
// placeholder — define Type 0x01 IMU and Type 0x02 RTT structs in TASK-05B

#ifndef PACKET_FORMAT_H
#define PACKET_FORMAT_H

#define PKT_IMU_LEN 40   // Type 0x01: fixed 40 bytes
// Type 0x02 RTT: variable — header 16 bytes + 16 bytes per AP

#endif // PACKET_FORMAT_H
