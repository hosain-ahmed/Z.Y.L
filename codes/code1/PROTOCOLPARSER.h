#ifndef PROTOCOLPARSER_H
#define PROTOCOLPARSER_H

#include <Arduino.h>

#define START_BYTE 0xAA
#define END_BYTE   0xBB

enum class ParseState { WAIT_START, WAIT_CMD, WAIT_PAYLOAD, WAIT_END };

struct Command {
  uint8_t cmdId;
  uint8_t payload;
};

class ProtocolParser {
  private:
    ParseState state = ParseState::WAIT_START;
    uint8_t pendingCmd;
    uint8_t pendingPayload;

  public:
    // Call this once per incoming byte. Returns true and fills 'out'
    // when a full valid packet has just been parsed.
    bool feed(uint8_t byte, Command &out) {
      switch (state) {
        case ParseState::WAIT_START:
          if (byte == START_BYTE) state = ParseState::WAIT_CMD;
          break;

        case ParseState::WAIT_CMD:
          pendingCmd = byte;
          state = ParseState::WAIT_PAYLOAD;
          break;

        case ParseState::WAIT_PAYLOAD:
          pendingPayload = byte;
          state = ParseState::WAIT_END;
          break;

        case ParseState::WAIT_END:
          state = ParseState::WAIT_START;  // reset regardless of outcome
          if (byte == END_BYTE) {
            out.cmdId = pendingCmd;
            out.payload = pendingPayload;
            return true;
          }
          break;
      }
      return false;
    }
};

#endif