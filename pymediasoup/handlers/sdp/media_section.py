import re
from typing import List
from dataclasses import dataclass
from aiortc import RTCIceParameters, RTCIceCandidate, RTCDtlsParameters
from ...producer import ProducerCodecOptions
from ...rtp_parameters import RtpParameters, RtpCodecParameters
from ...sctp_parameters import SctpParameters
from ...transport import PlainRtpParameters


def getCodecName(codec: RtpCodecParameters):
    pattern = re.compile(r'^(audio|video)/(.+)', re.I)
    match = pattern.match(codec.mimeType)
    if match:
        return match.group(2)
    else:
        raise TypeError('invalid codec.mimeType')

class MediaSection:
    def __init__(
        self,
        iceParameters: Optional[RTCIceParameters]=None,
        iceCandidates: List[RTCIceCandidate]=[],
        dtlsParameters: Optional[RTCDtlsParameters]=None,
        planB:bool=False
    ):
        self._mediaDict={}
        self._planB=planB
        if iceParameters:
            self.setIceParameters(iceParameters)
        if iceCandidates:
            self._mediaDict['candidates'] = []
            for candidate in iceCandidates:
                candidate.component = 1
                self._mediaDict['candidates'].append(dataclass.asdict(candidate))
            self._mediaDict['endOfCandidates'] = 'end-of-candidates'
            self._mediaDict['iceOptions'] = 'renomination'
        if dtlsParameters:
            self.setDtlsRole(dtlsParameters.role)
    
    @property
    def mid(self):
        return self._mediaDict.get('mid')
    
    @property
    def closed(self):
        return self._mediaDict.get('port') == 0
    
    def getDict(self):
        return self._mediaDict
    
    def setIceParameters(self, iceParameters: RTCIceParameters):
        self._mediaDict['iceUfrag'] = iceParameters.usernameFragment
        self._mediaDict['icePwd'] = iceParameters.password
    
    def disable(self):
        self._mediaDict['direction'] = 'inactive'
        del self._mediaDict['ext']
        del self._mediaDict['ssrcs']
        del self._mediaDict['ssrcGroups']
        del self._mediaDict['simulcast']
        del self._mediaDict['simulcast_03']
        del self._mediaDict['rids']
    
    def close(self):
        self._mediaDict['direction'] = 'inactive'
        self._mediaDict['port'] = 0
        del self._mediaDict['ext']
        del self._mediaDict['ssrcs']
        del self._mediaDict['ssrcGroups']
        del self._mediaDict['simulcast']
        del self._mediaDict['simulcast_03']
        del self._mediaDict['rids']
        del self._mediaDict['extmapAllowMixed']
    
class AnswerMediaSection(MediaSection):
    def __init__(
        self,
        sctpParameters: SctpParameters,
        offerMediaDict: dict,
        offerRtpParameters: RtpParameters,
        answerRtpParameters: RtpParameters,
        codecOptions: ProducerCodecOptions,
        iceParameters: Optional[RTCIceParameters]=None,
        iceCandidates: List[RTCIceCandidate]=[],
        dtlsParameters: Optional[RTCDtlsParameters]=None,
        plainRtpParameters: Optional[PlainRtpParameters]=None,
        planB: bool=False,
        extmapAllowMixed: bool=False
    ):
        super(AnswerMediaSection, self).__init__(iceParameters, iceCandidates, dtlsParameters, planB)
        self._mediaDict['mid'] = offerMediaDict.get('mid')
        self._mediaDict['type'] = offerMediaDict.get('type')
        self._mediaDict['protocol'] = offerMediaDict.get('protocol')

        if not plainRtpParameters:
            self._mediaDict['connection'] = {
                'ip': '127.0.0.1',
                'version': 4
            }
            self._mediaDict['port'] = 7
        else:
            self._mediaDict['connection'] = {
                'ip': plainRtpParameters.ip,
                'version': plainRtpParameters.ipVersion
            }
            self._mediaDict['port'] = plainRtpParameters.port
        
        if offerMediaDict.get('type') in ['audio', 'video']:
            self._mediaDict['direction'] = 'recvonly'
            self._mediaDict['rtp'] = []
            self._mediaDict['rtcpFb'] = []
            self._mediaDict['fmtp'] = []
            for codec in answerRtpParameters.codecs:
                rtp = {
                    'payload': codec.payloadType,
                    'codec': getCodecName(codec),
                    'rate': codec.clockRate
                }
                if (codec.channels > 1):
                    rtp['encoding'] = codec.channels
                self._mediaDict['rtp'].append(rtp)
                codecParameters = codec.parameters
                if codecOptions:
                    offerCodecs = [offerRtpCodec for offerRtpCodec in offerRtpParameters.codecs if offerRtpCodec.payloadType == codec.payloadType]
                    if offerCodecs:
                        offerCodec:RtpCodecParameters = offerCodecs[0]
                        if codec.mimeType.lower() == 'audio/opus':
                            if codecOptions.opusStereo != None:
                                offerCodec.parameters['sprop-stereo'] = 1 if codecOptions.opusStereo else 0
                                codecParameters['stereo'] = 1 if codecOptions.opusStereo else 0
                            if codecOptions.opusFec != None:
                                offerCodec.parameters['useinbandfec'] = 1 if codecOptions.opusFec else 0
                                codecParameters['useinbandfec'] = 1 if codecOptions.opusFec else 0
                            if codecOptions.opusDtx != None:
                                offerCodec.parameters['usedtx'] = 1 if codecOptions.opusDtx else 0
                                codecParameters['usedtx'] = 1 if codecOptions.opusDtx else 0
                            if codecOptions.opusMaxPlaybackRate != None:
                                codecParameters['maxplaybackrate'] = codecOptions.opusMaxPlaybackRate
                            if codecOptions.opusPtime != None:
                                offerCodec.parameters['ptime'] = codecOptions.opusPtime
                                codecParameters['ptime'] = codecOptions.opusPtime
                        elif codec.mimeType.lower() in ['video/vp8', 'video/vp9', 'video/h264', 'video/h265']:
                            if codecOptions.videoGoogleStartBitrate != None:
                                codecParameters['x-google-start-bitrate'] = codecOptions.videoGoogleStartBitrate
                            if codecOptions.videoGoogleMaxBitrate != None:
                                codecParameters['x-google-max-bitrate'] = codecOptions.videoGoogleMaxBitrate
                            if codecOptions.videoGoogleMinBitrate != None:
                                codecParameters['x-google-min-bitrate'] = codecOptions.videoGoogleMinBitrate
                fmtp = {
                    'payload': codec.payloadType,
                    'config': ';'.join([f'{key}={value}' for key, value in codecParameters.items()])
                }
                if fmtp['config']:
                    self._mediaDict['fmtp'].append(fmtp)
                for fb in codec.rtcpFeedback:
                    self._mediaDict['rtcpFb'].append({
                        'payload': codec.payloadType,
                        'type': fb.type,
                        'subtype': fb.parameter
                    })
            
            self._mediaDict['payloads'] = ' '.join([codec.payloadType for codec in answerRtpParameters.codecs])
            self._mediaDict['ext'] = []
            for ext in answerRtpParameters.headerExtensions:
                # Don't add a header extension if not present in the offer.
                if ext.uri in [localExt['uri'] for localExt in offerMediaDict['ext']]:
                    self._mediaDict['ext'].append({
                        'uri': ext.uri,
                        'value': ext.id
                    })
            # Allow both 1 byte and 2 bytes length header extensions.
            if extmapAllowMixed and offerMediaDict.get('extmapAllowMixed') == 'extmap-allow-mixed':
                self._mediaDict['extmapAllowMixed'] = 'extmap-allow-mixed'
            # Simulcast.
            if offerMediaDict.get('simulcast'):
                self._mediaDict['simulcast'] = {
                    'dir1': 'recv',
                    'list1': offerMediaDict.get('simulcast').get('list1')
                }
                self._mediaDict['rids'] = []
                if offerMediaDict.get('rids'):
                    for rid in offerMediaDict.get('rids'):
                        if rid.get('direction') == 'send':
                            self._mediaDict['rids'].append({
                                'id': rid.get('id'),
                                'direction': 'recv'
                            })
            # Simulcast (draft version 03).
            elif offerMediaDict.get('simulcast_03'):
                self._mediaDict['simulcast_03'] = {
                    'value': offerMediaDict.get('simulcast_03').get('value').replace('send', 'recv')
                }
                self._mediaDict['rids'] = []
                if offerMediaDict.get('rids'):
                    for rid in offerMediaDict.get('rids'):
                        if rid.get('direction') == 'send':
                            self._mediaDict['rids'].append({
                                'id': rid.get('id'),
                                'direction': 'recv'
                            })
            self._mediaDict['rtcpMux'] = 'rtcp-mux'
            self._mediaDict['rtcpRsize'] = 'rtcp-rsize'
            if self._planB and self._mediaDict.get('type') == 'video':
                self._mediaDict['xGoogleFlag'] = 'conference'
            
        elif offerMediaDict.get('type') == 'application':
            # New spec.
            if offerMediaDict.get('sctpPort'):
                self._mediaDict['payloads'] = 'webrtc-datachannel'
                self._mediaDict['sctpPort'] = sctpParameters.port
                self._mediaDict['maxMessageSize'] = sctpParameters.maxMessageSize
            # Old spec.
            elif offerMediaDict.get('sctpmap'):
                self._mediaDict['payloads'] = SctpParameters.port
                self._mediaDict['sctpmap'] = {
                    'app': 'webrtc-datachannel',
                    'sctpmapNumber': sctpParameters.port,
                    'maxMessageSize': sctpParameters.maxMessageSize
                }
    def setDtlsRole(self, role: str):
        if role == 'client':
            self._mediaDict['setup'] = 'active'
        elif role == 'server':
            self._mediaDict['setup'] = 'passive'
        elif role == 'auto':
            self._mediaDict['setup'] = 'actpass'

class OfferMediaSection(MediaSection):
    def __init__(
        self,
        sctpParameters: SctpParameters,
        offerRtpParameters: RtpParameters,
        mid: str,
        kind: Literal['audio', 'video', 'application'],
        streamId: Optional[str]=None,
        trackId: Optional[str]=None,
        oldDataChannelSpec: Optional[bool]=False,
        iceParameters: Optional[RTCIceParameters]=None,
        iceCandidates: List[RTCIceCandidate]=[],
        dtlsParameters: Optional[RTCDtlsParameters]=None,
        plainRtpParameters: Optional[PlainRtpParameters]=None,
        planB: bool=False,    
    ):
        super(OfferMediaSection, self).__init__(iceParameters, iceCandidates, dtlsParameters, planB)
        self._mediaDict['mid'] = mid
        self._mediaDict['type'] = kind
        if not plainRtpParameters:
            self._mediaDict['connection'] = {
                'ip': '127.0.0.1',
                'version': 4
            }
            if not sctpParameters:
                self._mediaDict['protocol'] = 'UDP/TLS/RTP/SAVPF'
            else:
                self._mediaDict['protocol'] = 'UDP/DTLS/SCTP'
            self._mediaDict['port'] = 7
        else:
            self._mediaDict['connection'] = {
                'ip': plainRtpParameters.ip,
                'version': plainRtpParameters.ipVersion
            }
            self._mediaDict['protocol'] = 'RTP/AVP'
            self._mediaDict['port'] = plainRtpParameters.port
        
        if kind in ['audio', 'video']:
            self._mediaDict['direction'] = 'sendonly'
            self._mediaDict['rtp'] = []
            self._mediaDict['rtcpFb'] = []
            self._mediaDict['fmtp'] = []
            if not self._planB:
                self._mediaDict['msid'] = f"{streamId if streamId else '-'} {trackId}"
            for codec in offerRtpParameters.codecs:
                rtp = {
                    'payload': codec.payloadType,
                    'codec': getCodecName(codec),
                    'rate': codec.clockRate
                }
                if codec.channels > 1:
                    rtp['encoding'] = codec.channels
                self._mediaDice['rtp'].append(rtp)
                fmtp = {
                    'payload': codec.payloadType,
                    'config': ';'.join([f'{key}={value}' for key, value in codec.parameters.items()])
                }
                if fmtp['config']:
                    self._mediaDict['fmtp'].append(fmtp)
                for fb in codec.rtcpFeedback:
                    self._mediaDict['rtcpFb'].append({
                        'payload': codec.payloadType,
                        'type': fb.type,
                        'subtype': fb.parameter
                    })
            
            self._mediaDict['payloads'] = ' '.join([codec.payloadType for codec in offerRtpParameters.codecs])
            self._mediaDict['ext'] = []
            for ext in offerRtpParameters.headerExtensions:
                self._mediaDict['ext'].append({
                    'uri': ext.uri,
                    'value': ext.id
                })
            
            self._mediaDict['rtcpMux'] = 'rtcp-mux'
            self._mediaDict['rtcpRsize'] = 'rtcp-rsize'
            encoding: RtpEncodingParameters = offerRtpParameters.encodings[0]
            ssrc = encoding.ssrc
            rtxSsrc = encoding.rtx.ssrc if encoding.rtx and encoding.rtx.ssrc else None
            self._mediaDict['ssrcs'] = []
            self._mediaDict['ssrcGroups'] = []
            if offerRtpParameters.rtcp.cname:
                self._mediaDict['ssrcs'].append({
                    'id': ssrc,
                    'attribute': 'cname',
                    'value': offerRtpParameters.rtcp.cname
                })
            if self._planB:
                self._mediaDict['ssrcs'].append({
                    'id': ssrc,
                    'attribute': 'msid',
                    'value': f"{streamId if streamId else '-'} {trackId}"
                })
            if rtxSsrc:
                if offerRtpParameters.rtcp.cname:
                    self._mediaDict['ssrcs'].append({
                        'id': rtxSsrc,
                        'attribute': 'cname',
                        'value': offerRtpParameters.rtcp.cname
                    })
                if self._planB:
                    self._mediaDict['ssrcs'].append({
                        'id': rtxSsrc,
                        'attribute': 'msid',
                        'value': f"{streamId if streamId else '-'} {trackId}"
                    })
                self._mediaDict['ssrcGroups'].append({
                    'semantics': 'FID',
                    'ssrcs': f'{ssrc} {rtxSsrc}'
                })
        elif kind == 'application':
            # New spec.
            if not oldDataChannelSpec:
                self._mediaDict['payloads'] = 'webrtc-datachannel'
                self._mediaDict['sctpPort'] = sctpParameters.port
                self._mediaDict['maxMessageSize'] = sctpParameters.maxMessageSize
            # Old spec.
            else:
                self._mediaDict['payloads'] = sctpParameters.port
                self._mediaDict['sctpmap'] = {
                    'app': 'webrtc-datachannel',
                    'sctpmapNumber': sctpParameters.port,
                    'maxMessageSize': sctpParameters.maxMessageSize
                }
    def setDtlsRole(self, _):
        # Always 'actpass'.
        self._mediaObject.setup = 'actpass'
    
    def planBReceive(self, offerRtpParameters: RtpParameters, streamId: str, trackId: str):
        encoding = offerRtpParameters.encodings[0]
        ssrc = encoding.ssrc
        rtxSsrc = encoding.rtx.ssrc if encoding.rtx and encoding.rtx.ssrc else None
        if offerRtpParameters.rtcp.cname:
            self._mediaDict['ssrcs'].append({
                'id': ssrc,
                'attribute': 'cname',
                'value': offerRtpParameters.rtcp.cname
            })
        self._mediaDict['ssrcs'].append({
            'id': ssrc,
            'attribute': 'msid',
            'value': f"{streamId if streamId else '-'} {trackId}"
        })
        if rtxSsrc:
            if offerRtpParameters.rtcp.cname:
                self._mediaDict['ssrcs'].append({
                    'id': rtxSsrc,
                    'attribute': 'cname',
                    'value': offerRtpParameters.rtcp.cname
                })
            self._mediaDict['ssrcs'].append({
                'id': rtxSsrc,
                'attribute': 'msid',
                'value': f"{streamId if streamId else '-'} {trackId}"
            })
            self._mediaDict['ssrcGroups'].append({
                'semantics': 'FID',
                'ssrcs': f'{ssrc} {rtxSsrc}'
            })