"""
This module contains the EVCC's State used to process the SECC's
SupportedAppProtocolRes. These states are independent of the protocol
(DIN SPEC 70121 or ISO 15118 protocol), as the EVCC and SECC use the
SupportedAppProtocolReq and -Res message pair to mutually agree upon a protocol.
"""

import logging.config
import time
from typing import Union, Type

from iso15118.evcc import evcc_settings
from iso15118.evcc.evcc_settings import SUPPORTED_PROTOCOLS
from iso15118.evcc.states.evcc_state import StateEVCC
from iso15118.evcc.states.iso15118_2_states import (SessionSetup
                                                    as SessionSetupV2)
from iso15118.evcc.states.iso15118_20_states import (SessionSetup
                                                     as SessionSetupV20)
from iso15118.evcc.comm_session_handler import EVCCCommunicationSession
from iso15118.shared import settings
from iso15118.shared.exceptions import MessageProcessingError
from iso15118.shared.messages.timeouts import Timeouts as TimeoutsShared
from iso15118.shared.messages.app_protocol import SupportedAppProtocolRes, \
    SupportedAppProtocolReq
from iso15118.shared.messages.enums import Protocol, Namespace
from iso15118.shared.messages.iso15118_2.timeouts import Timeouts
from iso15118.shared.messages.iso15118_2.body import (SessionSetupReq
                                                      as SessionSetupReqV2,
                                                      BodyBase)
from iso15118.shared.messages.iso15118_2.msgdef import (
    V2GMessage as V2GMessageV2)
from iso15118.shared.messages.iso15118_20.common_types import (
    MessageHeader as MessageHeaderV20,
    V2GMessage as V2GMessageV20, V2GRequest)
from iso15118.shared.messages.iso15118_20.common_messages import \
    SessionSetupReq as SessionSetupReqV20
from iso15118.shared.states import Terminate, State

logging.config.fileConfig(fname=settings.LOGGER_CONF_PATH,
                          disable_existing_loggers=False)
logger = logging.getLogger(__name__)


class SupportedAppProtocol(StateEVCC):
    """
    The state in which the EVCC processes a SupportedAppProtocolRes from
    the SECC to agree upon a mutually supported ISO 15118 version.
    """

    def __init__(self, comm_session: EVCCCommunicationSession):
        # TODO: less the time used for waiting for and processing the
        #       SDPResponse
        super().__init__(comm_session,
                         TimeoutsShared.SUPPORTED_APP_PROTOCOL_REQ)

    def process_message(self, message: Union[SupportedAppProtocolReq,
                                             SupportedAppProtocolRes,
                                             V2GMessageV2,
                                             V2GMessageV20]):
        msg = self.check_msg(message, SupportedAppProtocolRes, SupportedAppProtocolRes)
        if not msg:
            return

        sap_res: SupportedAppProtocolRes = msg

        next_msg: Union[SupportedAppProtocolReq,
                        SupportedAppProtocolRes,
                        BodyBase,
                        V2GRequest] = \
            SessionSetupReqV2(evcc_id=self.comm_session.ev_controller.get_evcc_id(
                Protocol.ISO_15118_2))
        next_ns: Namespace = Namespace.ISO_V2_MSG_DEF
        next_state: Type[State] = Terminate  # some default that is not None
        match = False

        for protocol in self.comm_session.supported_protocols:
            if protocol.schema_id == sap_res.schema_id:
                match = True
                if protocol.protocol_ns == Protocol.ISO_15118_2.ns.value:
                    self.comm_session.protocol = Protocol.ISO_15118_2
                    self.comm_session.session_id = self.get_session_id()
                    # next_msg is already set to SessionSetupReqV2 as default
                    next_state = SessionSetupV2
                elif protocol.protocol_ns.startswith(Namespace.ISO_V20_BASE):
                    self.comm_session.protocol = \
                        Protocol.get_by_ns(protocol.protocol_ns)
                    header = MessageHeaderV20(session_id=self.get_session_id(),
                                              timestamp=time.time())
                    next_msg = SessionSetupReqV20(
                        header=header,
                        evcc_id=self.comm_session.ev_controller.get_evcc_id(
                            self.comm_session.protocol)
                    )
                    next_ns = Namespace.ISO_V20_COMMON_MSG
                    next_state = SessionSetupV20
                else:
                    # This should not happen because the EVCC previously
                    # should have sent a valid SupportedAppProtocolReq
                    logger.error(
                        "EVCC sent an invalid protocol namespace in "
                        f"its previous SupportedAppProtocolReq: "
                        f"{protocol.protocol_ns}. Allowed "
                        f"namespaces are: {SUPPORTED_PROTOCOLS}")
                    raise MessageProcessingError('SupportedAppProtocolReq')
                break

        if match:
            logger.debug(f"Chosen protocol: {self.comm_session.protocol}")
            self.create_next_message(next_state,
                                     next_msg,
                                     Timeouts.SESSION_SETUP_REQ,
                                     next_ns)
            return

        self.stop_state_machine("SupportedAppProtocolRes with positive response "
                                f"{sap_res.response_code}' contains unmatched schema "
                                f"ID '{sap_res.schema_id}'")

    def get_session_id(self) -> str:
        """
        Check if there's a saved session ID from a previously paused charging
        session and applies that for the now resumed charging session.
        If there's no stored session ID, we'll set the session ID equal to zero.
        The session ID is also stored as a comm session variable.
        """
        if evcc_settings.RESUME_SESSION_ID:
            self.comm_session.session_id = evcc_settings.RESUME_SESSION_ID
            evcc_settings.RESUME_SESSION_ID = None
        else:
            self.comm_session.session_id = bytes(1).hex().upper()

        return self.comm_session.session_id
