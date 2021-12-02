
import binascii
import logging.config
import json
import os

from builtins import Exception
from py4j.java_gateway import JavaGateway
from iso15118.shared.messages.enums import Protocol
from iso15118.shared import settings

logging.config.fileConfig(fname=settings.LOGGER_CONF_PATH,
                          disable_existing_loggers=False)
logger = logging.getLogger(__name__)


def compare_messages(json_to_encode, decoded_json):
    json_obj = json.loads(json_to_encode)
    decoded_json_obj = json.loads(decoded_json)
    return sorted(json_obj.items()) == sorted(decoded_json_obj.items())


class ExiCodec:
    def __init__(self):
        logging.getLogger("py4j").setLevel(logging.CRITICAL)
        path_to_jar_file = os.path.join(settings.ROOT_DIR,
                                        "../shared/EXICodec.jar")
        self.gateway = JavaGateway.launch_gateway(
            classpath=path_to_jar_file,
            die_on_exit=False,
            javaopts=["--add-opens", "java.base/java.lang=ALL-UNNAMED"])

        self.exi_codec = self.gateway.jvm.com.siemens.ct.exi.main.cmd.EXICodec()

        self.protocol_schema_mapping = {
            '': self.gateway.jvm.com.siemens.ct.exi.main.cmd.BuiltInSchema.AppProtocol,
            'urn:iso:15118:2:2013:MsgDef': self.gateway.jvm.com.siemens.ct.exi.main.cmd.BuiltInSchema.ISO15118_2,
            'urn:iso:std:iso:15118:-20:CommonMessages':
                self.gateway.jvm.com.siemens.ct.exi.main.cmd.BuiltInSchema.ISO15118_20_V2G_CI_CommonMessages,
            'urn:iso:std:iso:15118:-20:AC':
                self.gateway.jvm.com.siemens.ct.exi.main.cmd.BuiltInSchema.ISO15118_20_V2G_CI_AC,
            'urn:iso:std:iso:15118:-20:DC':
                self.gateway.jvm.com.siemens.ct.exi.main.cmd.BuiltInSchema.ISO15118_20_V2G_CI_DC,
            'urn:iso:std:iso:15118:-20:WPT':
                self.gateway.jvm.com.siemens.ct.exi.main.cmd.BuiltInSchema.ISO15118_20_V2G_CI_WPT,
            'urn:iso:std:iso:15118:-20:ACDP':
                self.gateway.jvm.com.siemens.ct.exi.main.cmd.BuiltInSchema.ISO15118_20_V2G_CI_ACDP,
            'http://www.w3.org/2000/09/xmldsig#':
                self.gateway.jvm.com.siemens.ct.exi.main.cmd.BuiltInSchema.XSDCore
        }

        logger.debug(f"EXICodec version: {self.exi_codec.get_version()}")

    def encode(self, json_message, schema_ns: str) -> bytes:
        """
        Calls the Exificient EXI implmentation to encode input json.
        Returns a byte[] for the input message if conversion was successful.
        """
        java_schema_id = self.get_schema(schema_ns)
        exi = self.exi_codec.encode(json_message, java_schema_id)

        if exi is None:
            raise Exception(self.exi_codec.get_last_encoding_error())
        return exi

    def decode(self, exi_stream, namespace: str) -> str:
        """
        Calls the EXIficient EXI implementation to decode the input EXI stream.
        Returns a JSON representation of the input EXI stream if the conversion
        was successful.
        """
        java_schema_id = self.get_schema(namespace)
        decoded_message = self.exi_codec.decode(exi_stream, java_schema_id)

        if decoded_message is None:
            raise Exception(self.exi_codec.get_last_decoding_error())
        return decoded_message

    def encode_signed_info(self, json_message) -> bytes:
        """
        This method is added specifically to encode SignedInfoType that uses
        XSDCore schema
        """
        exi = self.exi_codec.encode_signed_info(json_message)

        if exi is None:
            raise Exception(self.exi_codec.get_last_encoding_error())
        return exi

    def decode_signed_info(self, exi_stream) -> str:
        """
        This method is added specifically to decode SignedInfoType that uses
        XSDCore schema
        """
        decoded_message = self.exi_codec.decode_signed_info(exi_stream)

        if decoded_message is None:
            raise Exception(self.exi_codec.get_last_decoding_error())
        return decoded_message

    def test_encode_decode_cycle(self, json_message, protocol: Protocol) -> bool:
        """
        This method is added to help test new messages.
        Perform an encode-decode cycle of the Json passed in.
        Returns true if both input and output Jsons are a match.
        This also helps validate against RISE V2G implementation of the EXI codec.
        """
        exi = self.encode(json_message, protocol.ns)
        if exi is not None:
            decoded_json = self.decode(exi, protocol.ns)
            if decoded_json is not None:
                if compare_messages(json_message, decoded_json):
                    return True

                logger.debug(f"JSON to encode: {json_message}"
                             f"\nDecoded JSON: {decoded_json}")
                return False
            else:
                logger.debug(f"Encoding worked: {exi.hex()}")
                logger.debug("Decoding error: "
                             f"{self.exi_codec.get_last_decoding_error()}")
        else:
            logger.debug("Encoding error: "
                         f"{self.exi_codec.get_last_encoding_error()}")

        return False

    def get_schema(self, schema_ns: str):
        """
        This maps Protocol to its corresponding enum value in the Exificient
        code. Defaults to AppProtocol if the passed in Protocol namespace is
        not present.
        """
        return self.protocol_schema_mapping.get(
            schema_ns,
            self.gateway.jvm.com.siemens.ct.exi.main.cmd.BuiltInSchema.AppProtocol)
