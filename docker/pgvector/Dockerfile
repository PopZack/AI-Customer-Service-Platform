# 本地构建 pgvector 镜像(替代 docker pull pgvector/pgvector:pg16)。
#
# 为什么需要本地构建:国内网络直连 registry-1.docker.io 超时,各公共镜像源也不稳定;
# 而 Alpine apk 源可达(换清华 TUNA 镜像,默认 CDN 实测仅 ~14KB/s)、
# GitHub 源码由宿主机下载后 COPY 进来 —— 整个构建零对 docker.io 的依赖。
#
# 构建产物与官方 pgvector/pgvector:pg16 等价(同为 PG16 + vector 扩展)。
# 用法:docker build -t pgvector/pgvector:pg16 docker/pgvector/
# (tag 成同名镜像后 docker-compose 直接复用本地镜像,不再尝试 pull)
FROM postgres:16-alpine

# 默认 CDN 在国内极慢,换清华 TUNA 镜像源(实测差两个数量级)
RUN sed -i 's/dl-cdn.alpinelinux.org/mirrors.tuna.tsinghua.edu.cn/g' /etc/apk/repositories

# pgvector v0.8.0 源码包(由宿主机下载,构建时 COPY 进来)
COPY pgvector-v0.8.0.tar.gz /tmp/pgvector.tar.gz

RUN apk add --no-cache --virtual .build-deps build-base postgresql16-dev \
    && tar -xzf /tmp/pgvector.tar.gz -C /tmp \
    # OPTFLAGS="":禁用 CPU 架构相关优化(SSE/AVX),保证镜像可移植
    # with_llvm=no:跳过 LLVM bitcode 编译。
    #   两个 make 都必须传!postgres:16-alpine 里的 PG 是 --with-llvm 构建的,
    #   PGXS 会尝试用 clang-21 编译 .bc 文件;镜像里没有该编译器,
    #   只给第一条 make 传则 install 阶段会重新触发 bitcode 编译而失败。
    && make -C /tmp/pgvector-0.8.0 OPTFLAGS="" with_llvm=no \
    && make -C /tmp/pgvector-0.8.0 install with_llvm=no \
    && rm -rf /tmp/pgvector.tar.gz /tmp/pgvector-0.8.0 \
    && apk del .build-deps
