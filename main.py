import json
import logging
import os
import re
import sys

import docker
import redis

_EXPOSE_ENABLE_LABEL = 'expose'
_EXPOSE_PORT_LABEL = 'expose.port'
_EXPOSE_HOST_LABEL = 'expose.host'

REDIS_URL = os.environ.get('REDIS_URL', 'redis://redis:6379')

try:
    DEFAULT_DOMAIN = os.environ['DEFAULT_DOMAIN']
except KeyError:
    logging.critical('required env var `DEFAULT_DOMAIN` is not set')
    sys.exit(1)

try:
    docker_client = docker.from_env()
except Exception as e:
    logging.error('failed to instantiate docker client: %s', e)
    sys.exit(1)


try:
    redis_client = redis.Redis.from_url(REDIS_URL)
    redis_client.info()
except Exception as e:
    logging.exception('failed instantiate redis client')
    sys.exit(1)


def enumerate_nodes():
    return enumerate([
        n.attrs['Status']['Addr']
        for n in docker_client.nodes.list()
        if n.attrs['Status']['State'] == 'ready'
    ])


def get_host_port(service):
    if 'Labels' not in service.attrs['Spec']:
        return None

    if 'Ports' not in service.attrs['Endpoint']:
        return None

    labels = service.attrs['Spec']['Labels']
    endpoint_ports = service.attrs['Endpoint']['Ports']

    if len(endpoint_ports) == 0:
        logging.error('service %s does not publish any port', service.name,)
        return None

    host = labels.get(_EXPOSE_HOST_LABEL) or f'{service.name}.{DEFAULT_DOMAIN}'
    target_port = labels.get(_EXPOSE_PORT_LABEL)

    if len(endpoint_ports) == 1:
        port = endpoint_ports[0]['PublishedPort']
    elif not target_port:
        port = [p['PublishedPort'] for p in endpoint_ports][0]
    else:
        published_ports = [p['PublishedPort'] for p in endpoint_ports if p['TargetPort'] == target_port]
        if not published_ports:
            logging.error('service %s does not publish port %s', service.name, target_port)
            return None
        port = published_ports[0]

    return host, port


def set_service(service):
    name = service.name

    labels = service.attrs['Spec']['Labels']

    expose = bool(labels.get(_EXPOSE_ENABLE_LABEL, False))
    if not expose:
        remove_service(service)
        return
    
    host_port = get_host_port(service)
    if not host_port:
        return
    
    host, port = host_port

    logging.info(f'exposing service {name} with port {port} at {host}')

    with redis_client.pipeline() as p:
        for i, server in enumerate_nodes():
            p.set(f'traefik/http/services/{name}/loadbalancer/servers/{i}/url', f'http://{server}:{port}')
        p.set(f'traefik/http/routers/{name}/service', name)
        p.set(f'traefik/http/routers/{name}/rule', f'Host(`{host}`)')
        p.execute()


def remove_service(service):
    name = service.name

    delist = [
        *[f'traefik/http/services/{name}/loadbalancer/servers/{i}/url' for i, _ in enumerate_nodes()],
        f'traefik/http/routers/{name}/service',
        f'traefik/http/routers/{name}/rule',
    ]

    redis_client.delete(*delist)
        


def set_all():
    for service in docker_client.services.list():
        set_service(service)


def reset_all():
    for service in docker_client.services.list():
        remove_service(service)
        set_service(service)


reset_all()


for e in docker_client.events(filters={'scope': 'swarm'}, decode=True):
    if e['Type'] == 'service':
        if e['Action'] in ('create', 'update'):
            service = docker_client.services.get(e['Actor']['ID'])
            set_service(service)
        elif e['Action'] == 'remove':
            remove_service(e['Actor']['Attributes']['name'])
    elif e['type'] == 'node':
        if e['Action']  == 'create':
            set_all()
        elif e['Action'] in ('update', 'remove'):
            reset_all()
