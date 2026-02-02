FROM nginx:1.25-alpine

RUN apk add --no-cache \
    libmaxminddb \
    libmaxminddb-dev \
    && apk add --no-cache --virtual .build-deps \
    gcc \
    libc-dev \
    make \
    openssl-dev \
    pcre-dev \
    zlib-dev \
    linux-headers \
    curl \
    gnupg \
    git

RUN cd /tmp \
    && git clone --depth 1 https://github.com/leev/ngx_http_geoip2_module.git \
    && cd /tmp \
    && curl -fSL https://nginx.org/download/nginx-1.25.3.tar.gz -o nginx.tar.gz \
    && tar -zxC /tmp -f nginx.tar.gz \
    && cd /tmp/nginx-1.25.3 \
    && ./configure --with-compat --add-dynamic-module=/tmp/ngx_http_geoip2_module \
    && make modules \
    && cp objs/ngx_http_geoip2_module.so /usr/lib/nginx/modules/ \
    && rm -rf /tmp/nginx* /tmp/ngx_http_geoip2_module \
    && apk del .build-deps

RUN mkdir -p /usr/share/GeoIP

EXPOSE 80 443

CMD ["nginx", "-g", "daemon off;"]
