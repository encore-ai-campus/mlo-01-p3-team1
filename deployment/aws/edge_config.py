"""Render owner-only CloudFront configuration without contacting AWS.

Plan fields: project, environment, generation, alb_domain, viewer_cidr,
function_arn, policies ({cache, origin-request, response-headers}).
Secret fields: name and value, shared with the origin nginx configuration.
"""
import argparse
import ipaddress
import json
import os
from pathlib import Path
import re


def viewer_function(cidr):
    network=ipaddress.ip_network(cidr,strict=True)
    if network.version!=4 or network.prefixlen==0:
        raise ValueError('restricted_IPv4_viewer_CIDR_required')
    return """function handler(event) {
 var request=event.request, parts=event.viewer.ip.split('.'), address=0;
 if(parts.length!==4) return {statusCode:403,statusDescription:'Forbidden'};
 for(var i=0;i<4;i++){var n=Number(parts[i]);if(!/^\\d+$/.test(parts[i])||n<0||n>255)return {statusCode:403,statusDescription:'Forbidden'};address=((address<<8)|n)>>>0;}
 if(((address & MASK)>>>0)!==NETWORK || request.uri.indexOf('/api/internal/')===0) return {statusCode:403,statusDescription:'Forbidden',headers:{'cache-control':{value:'no-store'}}};
 return request;
}
""".replace('MASK',str(int(network.netmask))).replace('NETWORK',str(int(network.network_address)))


def distribution(plan, secret):
    if not re.fullmatch(r'[a-z0-9-]+\.[a-z0-9-]+\.elb\.amazonaws\.com',plan['alb_domain']):
        raise ValueError('owned_ALB_DNS_required')
    if not re.fullmatch(r'x-music-origin-[a-f0-9]{12}',secret['name']) or not re.fullmatch(r'[A-Za-z0-9_-]{40,}',secret['value']):
        raise ValueError('strong_origin_header_required')
    viewer_function(plan['viewer_cidr'])
    p=plan['policies']
    return {'CallerReference':plan['project']+'-'+plan['generation']+'-temporary-https',
        'Comment':plan['project']+' '+plan['environment']+' '+plan['generation']+' approved temporary HTTPS',
        'Origins':{'Quantity':1,'Items':[{'Id':'owned-alb','DomainName':plan['alb_domain'],'OriginPath':'',
          'CustomHeaders':{'Quantity':1,'Items':[{'HeaderName':secret['name'],'HeaderValue':secret['value']}]},
          'CustomOriginConfig':{'HTTPPort':80,'HTTPSPort':443,'OriginProtocolPolicy':'http-only','OriginSslProtocols':{'Quantity':1,'Items':['TLSv1.2']},'OriginReadTimeout':60,'OriginKeepaliveTimeout':5}}]},
        'DefaultCacheBehavior':{'TargetOriginId':'owned-alb','ViewerProtocolPolicy':'redirect-to-https',
          'AllowedMethods':{'Quantity':7,'Items':['GET','HEAD','OPTIONS','PUT','PATCH','POST','DELETE'],'CachedMethods':{'Quantity':2,'Items':['GET','HEAD']}},
          'CachePolicyId':p['cache'],'OriginRequestPolicyId':p['origin-request'],
          'ResponseHeadersPolicyId':p['response-headers'],'Compress':True,
          'FunctionAssociations':{'Quantity':1,'Items':[{'FunctionARN':plan['function_arn'],'EventType':'viewer-request'}]}},
        'Enabled':True,'ViewerCertificate':{'CloudFrontDefaultCertificate':True},'HttpVersion':'http2','IsIPV6Enabled':False,
        'PriceClass':'PriceClass_All','Restrictions':{'GeoRestriction':{'RestrictionType':'none','Quantity':0}}}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--plan',type=Path,required=True)
    parser.add_argument('--secret',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    os.umask(0o077)
    plan=json.loads(args.plan.read_text());secret=json.loads(args.secret.read_text())
    result=distribution(plan,secret)
    args.output.mkdir(parents=True,exist_ok=True);args.output.chmod(0o700)
    for name,value in [('viewer-function.js',viewer_function(plan['viewer_cidr'])),('distribution-with-tags.json',json.dumps({'DistributionConfig':result,'Tags':{'Items':[{'Key':k,'Value':v} for k,v in {'Project':plan['project'],'Environment':plan['environment'],'Generation':plan['generation'],'Purpose':'temporary-application-https'}.items()]}},indent=2))]:
        target=args.output/name
        if target.is_symlink():raise ValueError('unsafe_output_path')
        target.write_text(value);target.chmod(0o600)
    print(json.dumps({'rendered':True,'AWS_changed':False,'new_ec2':0,'new_vpc':0}))


if __name__=='__main__':main()
