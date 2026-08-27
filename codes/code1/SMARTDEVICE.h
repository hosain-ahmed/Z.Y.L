#ifndef SMARTDEVICE_H
#define SMARTDEVICE_H


class SmartDevice{
    public: 
        virtual void handleCommand(char cmd) =0;
        virtual void update() = 0;
        virtual const char* getName() =0 ;

};

#endif