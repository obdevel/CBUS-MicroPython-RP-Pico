
# cbusdefs.py

## CBUS opcodes list

## Packets with no data bytes

OPC_ACK = 0x00  ## General ack
OPC_NAK = 0x01  ## General nak
OPC_HLT = 0x02  ## Bus Halt
OPC_BON = 0x03  ## Bus on
OPC_TOF = 0x04  ## Track off
OPC_TON = 0x05  ## Track on
OPC_ESTOP   = 0x06  ## Track stopped
OPC_ARST    = 0x07  ## System reset
OPC_RTOF    = 0x08  ## Request track off
OPC_RTON    = 0x09  ## Request track on
OPC_RESTP   = 0x0a  ## Request emergency stop all
OPC_RSTAT   = 0x0c  ## Request node status
OPC_QNN = 0x0d  ## Query nodes
## 
OPC_RQNP    = 0x10  ## Read node parameters
OPC_RQMN    = 0x11  ## Request name of module type
## 
## Packets with 1 data byte
## 
OPC_KLOC    = 0x21  ## Release engine by handle
OPC_QLOC    = 0x22  ## Query engine by handle
OPC_DKEEP   = 0x23  ## Keep alive for cab
## 
OPC_DBG1    = 0x30  ## Debug message with 1 status byte
OPC_EXTC    = 0x3F  ## Extended opcode
## 
## Packets with 2 data bytes
## 
OPC_RLOC    = 0x40  ## Request session for loco
OPC_QCON    = 0x41  ## Query consist
OPC_SNN = 0x42  ## Set node number
OPC_ALOC = 0x43 ## Allocate loco (used to allocate to a shuttle in cancmd)
## 
OPC_STMOD   = 0x44  ## Set Throttle mode
OPC_PCON    = 0x45  ## Consist loco
OPC_KCON    = 0x46  ## De-consist loco
OPC_DSPD    = 0x47  ## Loco speed/dir
OPC_DFLG    = 0x48  ## Set engine flags
OPC_DFNON   = 0x49  ## Loco function on
OPC_DFNOF   = 0x4A  ## Loco function off
OPC_SSTAT   = 0x4C  ## Service mode status
OPC_NNRSM   = 0x4F  ## Reset to manufacturer's defaults
## 
OPC_RQNN    = 0x50  ## Request Node number in setup mode
OPC_NNREL   = 0x51  ## Node number release
OPC_NNACK   = 0x52  ## Node number acknowledge
OPC_NNLRN   = 0x53  ## Set learn mode
OPC_NNULN   = 0x54  ## Release learn mode
OPC_NNCLR   = 0x55  ## Clear all events
OPC_NNEVN   = 0x56  ## Read available event slots
OPC_NERD    = 0x57  ## Read all stored events
OPC_RQEVN   = 0x58  ## Read number of stored events
OPC_WRACK   = 0x59  ## Write acknowledge
OPC_RQDAT   = 0x5A  ## Request node data event
OPC_RQDDS   = 0x5B  ## Request short data frame
OPC_BOOT    = 0x5C  ## Put node into boot mode
OPC_ENUM    = 0x5D  ## Force can_id self enumeration
OPC_NNRST   = 0x5E  ## Reset node (as in restart)
OPC_EXTC1   = 0x5F  ## Extended opcode with 1 data byte
## 
## Packets with 3 data bytes
## 
OPC_DFUN    = 0x60  ## Set engine functions
OPC_GLOC    = 0x61  ## Get loco (with support for steal/share)
OPC_ERR = 0x63  ## Command station error
OPC_CMDERR  = 0x6F  ## Errors from nodes during config
## 
OPC_EVNLF   = 0x70  ## Event slots left response
OPC_NVRD    = 0x71  ## Request read of node variable
OPC_NENRD   = 0x72  ## Request read stored event by index
OPC_RQNPN   = 0x73  ## Request read module parameters
OPC_NUMEV   = 0x74  ## Number of events stored response
OPC_CANID   = 0x75  ## Set canid
OPC_EXTC2   = 0x7F  ## Extended opcode with 2 data bytes
## 
## Packets with 4 data bytes
## 
OPC_RDCC3   = 0x80  ## 3 byte DCC packet
OPC_WCVO    = 0x82  ## Write CV byte Ops mode by handle
OPC_WCVB    = 0x83  ## Write CV bit Ops mode by handle
OPC_QCVS    = 0x84  ## Read CV
OPC_PCVS    = 0x85  ## Report CV
## 
OPC_ACON    = 0x90  ## on event
OPC_ACOF    = 0x91  ## off event
OPC_AREQ    = 0x92  ## Accessory Request event
OPC_ARON    = 0x93  ## Accessory response event on
OPC_AROF    = 0x94  ## Accessory response event off
OPC_EVULN   = 0x95  ## Unlearn event
OPC_NVSET   = 0x96  ## Set a node variable
OPC_NVANS   = 0x97  ## Node variable value response
OPC_ASON    = 0x98  ## Short event on
OPC_ASOF    = 0x99  ## Short event off
OPC_ASRQ    = 0x9A  ## Short Request event
OPC_PARAN   = 0x9B  ## Single node parameter response
OPC_REVAL   = 0x9C  ## Request read of event variable
OPC_ARSON   = 0x9D  ## Accessory short response on event
OPC_ARSOF   = 0x9E  ## Accessory short response off event
OPC_EXTC3   = 0x9F  ## Extended opcode with 3 data bytes
## 
## Packets with 5 data bytes
## 
OPC_RDCC4   = 0xA0  ## 4 byte DCC packet
OPC_WCVS    = 0xA2  ## Write CV service mode
## 
OPC_ACON1   = 0xB0  ## On event with one data byte
OPC_ACOF1   = 0xB1  ## Off event with one data byte
OPC_REQEV   = 0xB2  ## Read event variable in learn mode
OPC_ARON1   = 0xB3  ## Accessory on response (1 data byte)
OPC_AROF1   = 0xB4  ## Accessory off response (1 data byte)
OPC_NEVAL   = 0xB5  ## Event variable by index read response
OPC_PNN = 0xB6  ## Response to QNN
OPC_ASON1   = 0xB8  ## Accessory short on with 1 data byte
OPC_ASOF1   = 0xB9  ## Accessory short off with 1 data byte
OPC_ARSON1  = 0xBD  ## Short response event on with one data byte
OPC_ARSOF1  = 0xBE  ## Short response event off with one data byte
OPC_EXTC4   = 0xBF  ## Extended opcode with 4 data bytes
## 
## Packets with 6 data bytes
## 
OPC_RDCC5   = 0xC0  ## 5 byte DCC packet
OPC_WCVOA   = 0xC1  ## Write CV ops mode by address
OPC_CABDAT  = 0xC2  ## Cab data (cab signalling)
OPC_FCLK    = 0xCF  ## Fast clock
## 
OPC_ACON2   = 0xD0  ## On event with two data bytes
OPC_ACOF2   = 0xD1  ## Off event with two data bytes
OPC_EVLRN   = 0xd2  ## Teach event
OPC_EVANS   = 0xd3  ## Event variable read response in learn mode
OPC_ARON2   = 0xD4  ## Accessory on response
OPC_AROF2   = 0xD5  ## Accessory off response
OPC_ASON2   = 0xD8  ## Accessory short on with 2 data bytes
OPC_ASOF2   = 0xD9  ## Accessory short off with 2 data bytes
OPC_ARSON2  = 0xDD  ## Short response event on with two data bytes
OPC_ARSOF2  = 0xDE  ## Short response event off with two data bytes
OPC_EXTC5   = 0xDF  ## Extended opcode with 5 data bytes
## 
## Packets with 7 data bytes
## 
OPC_RDCC6   = 0xE0  ## 6 byte DCC packets
OPC_PLOC    = 0xE1  ## Loco session report
OPC_NAME    = 0xE2  ## Module name response
OPC_STAT    = 0xE3  ## Command station status report
OPC_PARAMS  = 0xEF  ## Node parameters response
## 
OPC_ACON3   = 0xF0  ## On event with 3 data bytes
OPC_ACOF3   = 0xF1  ## Off event with 3 data bytes
OPC_ENRSP   = 0xF2  ## Read node events response
OPC_ARON3   = 0xF3  ## Accessory on response
OPC_AROF3   = 0xF4  ## Accessory off response
OPC_EVLRNI  = 0xF5  ## Teach event using event indexing
OPC_ACDAT   = 0xF6  ## Accessory data event: 5 bytes of node data (eg: RFID)
OPC_ARDAT   = 0xF7  ## Accessory data response
OPC_ASON3   = 0xF8  ## Accessory short on with 3 data bytes
OPC_ASOF3   = 0xF9  ## Accessory short off with 3 data bytes
OPC_DDES    = 0xFA  ## Short data frame aka device data event (device id plus 5 data bytes)
OPC_DDRS    = 0xFB  ## Short data frame response aka device data response
OPC_DDWS    = 0xFC  ## Device Data Write Short
OPC_ARSON3  = 0xFD  ## Short response event on with 3 data bytes
OPC_ARSOF3  = 0xFE  ## Short response event off with 3 data bytes
OPC_EXTC6   = 0xFF  ## Extended opcode with 6 data byes
##
## additions
##
OPC_DTXC = 0xE9
