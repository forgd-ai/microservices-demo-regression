# Build natively for the host architecture (Intel amd64 or Apple Silicon arm64),
# no emulation/cross-compile. Multi-arch SDK/runtime tags resolve to the host arch.
FROM public.ecr.aws/z8z1z1j0/workshop-base-images:mcr.microsoft.com-dotnet-sdk_10.0-noble AS builder
WORKDIR /app
COPY cartservice.csproj .
RUN dotnet restore cartservice.csproj -a $(dpkg --print-architecture)
COPY . .
RUN dotnet publish cartservice.csproj \
    -p:PublishSingleFile=true \
    -a $(dpkg --print-architecture) \
    --self-contained true \
    -p:PublishTrimmed=true \
    -p:TrimMode=full \
    -c release \
    -o /cartservice

FROM public.ecr.aws/z8z1z1j0/workshop-base-images:mcr.microsoft.com-dotnet-runtime-deps_10.0-noble-chiseled
WORKDIR /app
COPY --from=builder /cartservice .
EXPOSE 7070
ENV DOTNET_EnableDiagnostics=0 \
    ASPNETCORE_HTTP_PORTS=7070
USER 1000
ENTRYPOINT ["/app/cartservice"]
