#pragma once

#include <Arduino.h>
#include <OneWire.h>
#include "config.h"

class PowerManager {
public:
    void begin();

    // DS2413 channel control
    void setMD25Power(bool on);    // Ch.A -> IRLZ44N -> MD25
    void setPiPower(bool on);      // Ch.B -> IRF4905 -> Pi
    bool getMD25Power() const { return _md25On; }
    bool getPiPower() const { return _piOn; }

    // Pi GPIO shutdown/wake
    void initiatePiShutdown();     // signal Pi to shut down
    bool isPiShutdownComplete();   // true if Pi confirms shutdown (GPIO34 LOW)

    // High-level sequences (non-blocking, call from loop)
    void startShutdownSequence();
    void startWakeSequence();
    bool isSequenceRunning() const { return _seqState != SEQ_IDLE; }
    void updateSequence();         // call every loop() to advance sequence

private:
    OneWire _ow{PIN_ONEWIRE};
    uint8_t _ds2413Addr[8] = {};
    bool _ds2413Found = false;
    bool _md25On = false;
    bool _piOn = false;

    // Sequence state machine
    enum SeqState {
        SEQ_IDLE,
        SEQ_SHUTDOWN_SIGNAL_SENT,
        SEQ_SHUTDOWN_WAIT_PI,
        SEQ_SHUTDOWN_POWER_OFF,
        SEQ_WAKE_PI_ON,
        SEQ_WAKE_DONE,
    };
    SeqState _seqState = SEQ_IDLE;
    uint32_t _seqStartMs = 0;

    bool ds2413Write(bool chA, bool chB);
    void applyPower();
};
