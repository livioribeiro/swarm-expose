# Expose services on a Docker Swarm cluster using Traefik and Redis

Swarm-expose allows you to expose your services running on a docker swarm cluster without needing to give Treafik access to the docker socket. You can have a single Traefik instance load balancing requests between swarm nodes and the ingress network routes the requests to the services.

Usage:

Deploy the stack from [`stack.yml`](./stack.yml).

**IMPORTANT:** Change the value of the environment variable `DEFAULT_DOMAIN`

Start Traefik using the deployed Redis:

```sh
traefik --providers.redis.endpoints=<docker_node>:6379
```
Create a service, publish its port and add the label `expose=1`:

```sh
docker service create --name nginx --publish 80 --label expose=1 nginx
```

The service will be exposed as `http://${service.name}.${DEFAULT_DOMAIN}/`

To change the host for the service, add the label `expose.host=my-host`

```sh
docker service update nginx --label-add expose.host=my-host
```

The service will now be exposed as `http:/my-host`

If your service publishes more than one port, swarm-expose will get the first, unless you tell which one to expose using the label `expose.port`

```sh
docker service update nginx --publish-add 443 --label-add expose.port=443
```
