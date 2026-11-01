"""Hardware-decoded codec first. selkies offers its video codecs in its own
order (AV1, HEVC, H.264) and a browser answers with the first one it decodes at
all, software included; selkies then keeps that codec. A browser decoding AV1
in software (no AV1 hardware) stalls at high rates. This page shim reorders the
browser's answer (setCodecPreferences) so codecs the browser reports as
hardware-decoded (mediaCapabilities `powerEfficient`) come first, each group in
the offer's order; selkies moves the display to the answer's first codec. A
browser with no hardware codec, or one whose first offered codec is already
hardware-decoded, answers untouched."""

CODECPREF_JS = r"""<script id="styx-codecpref">(function(){try{
var P=window.RTCPeerConnection&&RTCPeerConnection.prototype,MC=navigator.mediaCapabilities;
if(!P||!P.createAnswer||!window.RTCRtpReceiver||!RTCRtpReceiver.getCapabilities||!MC||!MC.decodingInfo)return;
var memo={};
function hw(m){if(!(m in memo))memo[m]=Promise.race([MC.decodingInfo({type:'webrtc',video:{contentType:m,width:2560,height:1440,bitrate:3e7,framerate:60}})
.then(function(r){return !!(r&&r.supported&&r.powerEfficient)},function(){return false}),
new Promise(function(ok){setTimeout(function(){ok(false)},800)})]);return memo[m]}
function offered(sdp){var o=[],mv=/^m=video \d+ \S+ ([\d ]+)/m.exec(sdp||'');if(!mv)return o;
mv[1].trim().split(' ').forEach(function(pt){var r=new RegExp('^a=rtpmap:'+pt+' ([^/\\s]+)','m').exec(sdp);
if(r){var m='video/'+r[1].toLowerCase();if(o.indexOf(m)<0)o.push(m)}});return o}
function aux(m){return /\/(rtx|red|ulpfec|flexfec-03)$/.test(m)}
var ca=P.createAnswer;
P.createAnswer=function(){var pc=this,args=arguments;
try{var ts=pc.getTransceivers().filter(function(t){return t.receiver&&t.receiver.track&&t.receiver.track.kind==='video'&&t.setCodecPreferences}),
caps=(RTCRtpReceiver.getCapabilities('video')||{}).codecs||[],order=offered(pc.remoteDescription&&pc.remoteDescription.sdp);
if(!ts.length||!caps.length||!order.length)return ca.apply(pc,args);
var main=order.filter(function(m){return !aux(m)&&caps.some(function(c){return c.mimeType.toLowerCase()===m})});
return Promise.all(main.map(hw)).then(function(h){
var fast=main.filter(function(m,i){return h[i]});
if(!fast.length||fast[0]===main[0])return ca.apply(pc,args);
var rank=fast.concat(main.filter(function(m){return fast.indexOf(m)<0}));
function key(c){var i=rank.indexOf(c.mimeType.toLowerCase());return i<0?rank.length:i}
var pref=caps.map(function(c,i){return [c,i]}).sort(function(a,b){return key(a[0])-key(b[0])||a[1]-b[1]}).map(function(x){return x[0]});
ts.forEach(function(t){try{t.setCodecPreferences(pref)}catch(e){}});
try{fetch('styx/gamemode',{method:'POST',headers:{'Content-Type':'application/json'},
body:JSON.stringify({diag:{codecpref:rank,offered:main[0]}}),keepalive:true}).catch(function(){})}catch(e){}
return ca.apply(pc,args)},function(){return ca.apply(pc,args)})}catch(e){return ca.apply(pc,args)}};
}catch(e){}})();</script>"""


def inject_codecpref(html: str) -> str:
    """Before </head>, so the shim wraps createAnswer before selkies answers."""
    if "</head>" not in html:
        return html
    return html.replace("</head>", CODECPREF_JS + "</head>", 1)
