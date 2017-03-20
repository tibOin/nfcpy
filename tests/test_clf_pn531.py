# -*- coding: latin-1 -*-
from __future__ import absolute_import, division

import nfc
import nfc.clf
import nfc.clf.pn531

import pytest
from pytest_mock import mocker  # noqa: F401
from mock import call
from binascii import hexlify

import base_clf_pn53x
from base_clf_pn53x import CMD, RSP, ACK, NAK, ERR, HEX  # noqa: F401

import logging
logging.basicConfig(level=logging.DEBUG-1)  # WARN)
logging_level = logging.getLogger().getEffectiveLevel()
logging.getLogger("nfc.clf").setLevel(logging_level)
logging.getLogger("nfc.clf.pn531").setLevel(logging_level)


@pytest.fixture()  # noqa: F811
def transport(mocker):
    mocker.patch('nfc.clf.transport.USB.__init__').return_value = None
    transport = nfc.clf.transport.USB(1, 1)
    mocker.patch.object(transport, 'write', autospec=True)
    mocker.patch.object(transport, 'read', autospec=True)
    transport._manufacturer_name = "Manufacturer Name"
    transport._product_name = "Product Name"
    transport.context = None
    transport.usb_dev = None
    return transport


class TestChipset(base_clf_pn53x.TestChipset):
    @pytest.fixture()
    def chipset(self, transport):
        return nfc.clf.pn531.Chipset(transport, logger=nfc.clf.pn531.log)

    @pytest.mark.parametrize("mode, timeout, command", [
        ("normal", 0, CMD('14 01 00')),
        ("virtual", 1, CMD('14 02 01')),
        ("wired", 2, CMD('14 03 02')),
        ("dual", 3, CMD('14 04 03')),
    ])
    def test_sam_configuration(self, chipset, mode, timeout, command):
        chipset.transport.read.side_effect = [ACK(), RSP('15')]
        assert chipset.sam_configuration(mode, timeout) is None
        assert chipset.transport.write.mock_calls == [call(command)]
        assert chipset.transport.read.mock_calls == [call(100), call(100)]

    @pytest.mark.parametrize("wakeup_enable, command", [
        ("INT0", '16 01'), ("INT1", '16 02'), ("USB",  '16 04'),
        ("RF",   '16 08'), ("HSU",  '16 10'), ("SPI",  '16 20'),
        ("INT0, INT1, RF", '16 0B'), ("SPI, HSU, USB", '16 34'),
    ])
    def test_power_down(self, chipset, wakeup_enable, command):
        chipset.transport.read.side_effect = [ACK(), RSP('17 00')]
        assert chipset.power_down(wakeup_enable) is None
        assert chipset.transport.write.mock_calls == [call(CMD(command))]
        assert chipset.transport.read.mock_calls == [call(100), call(100)]
        chipset.transport.read.side_effect = [ACK(), RSP('17 01')]
        with pytest.raises(chipset.Error) as excinfo:
            chipset.power_down(wakeup_enable)
        assert excinfo.value.errno == 1

    def test_tg_init_tama_target(self, chipset):
        chipset.transport.read.side_effect = [ACK(), RSP('8D 01 02 03')]
        mifare = HEX('010203040506')
        felica = HEX('010203040506070809101112131415161718')
        nfcid3 = HEX('01020304050607080910')
        gbytes = HEX('313233')
        args = (0x03, mifare, felica, nfcid3, gbytes, 0.5)
        assert chipset.tg_init_tama_target(*args) == HEX('01 02 03')
        assert chipset.transport.read.mock_calls == [call(100), call(500)]
        assert chipset.transport.write.mock_calls == [
            call(CMD('8C 03 010203040506 010203040506070809101112131415161718'
                     '01020304050607080910 313233'))
        ]


class TestDevice:
    @pytest.fixture()
    def device(self, transport):
        transport.write.return_value = None
        transport.read.side_effect = [
            ACK(), RSP('01 00' + hexlify(bytearray(range(251)))),  # Diagnose
            ACK(), RSP('03 0304'),  # GetFirmwareVersion
            ACK(), RSP('15'),       # SAMConfiguration
            ACK(), RSP('13'),       # SetTAMAParameters
            ACK(), RSP('33'),       # RFConfiguration
            ACK(), RSP('33'),       # RFConfiguration
            ACK(), RSP('33'),       # RFConfiguration
            ACK(), RSP('33'),       # RFConfiguration
        ]
        device = nfc.clf.pn531.init(transport)
        assert isinstance(device, nfc.clf.pn531.Device)
        assert isinstance(device.chipset, nfc.clf.pn531.Chipset)
        assert transport.write.mock_calls == [call(_) for _ in [
            CMD('00 00' + hexlify(bytearray(range(251)))),  # Diagnose
            CMD('02'),            # GetFirmwareVersion
            CMD('14 0100'),       # SAMConfiguration
            CMD('12 00'),         # SetTAMAParameters
            CMD('32 02000b0a'),   # RFConfiguration
            CMD('32 0400'),       # RFConfiguration
            CMD('32 05010001'),   # RFConfiguration
            CMD('32 0102'),       # RFConfiguration
        ]]
        transport.write.reset_mock()
        transport.read.reset_mock()
        yield device
        transport.write.reset_mock()
        transport.read.reset_mock()
        transport.read.side_effect = [
            ACK(), RSP('33'),  # RFConfiguration
        ]
        device.close()
        assert transport.write.mock_calls == [
            call(CMD('32 0102')),  # RFConfiguration
        ]

    def test_sense_tta_no_target_found(self, device):
        device.chipset.transport.read.side_effect = [
            ACK(), RSP('4B 00'),  # InListPassiveTarget
            ACK(), RSP('07 26'),  # ReadRegister
        ]
        assert device.sense_tta(nfc.clf.RemoteTarget('106A')) is None
        assert device.chipset.transport.write.mock_calls == [
            call(CMD('4A 0100')),  # InListPassiveTarget
            call(CMD('06 6339')),  # ReadRegister
        ]
        pass