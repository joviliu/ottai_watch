#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
mkdir -p .sign watch/sign/debug watch/sign/release
if [ ! -f .sign/private.pem ]; then
  openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -out .sign/private.pem
fi
if [ ! -f .sign/certificate.pem ]; then
  openssl req -new -x509 -key .sign/private.pem -out .sign/certificate.pem -days 3650 -subj '/CN=Personal GlucoseWatch6/O=Personal Development'
fi
cp .sign/private.pem watch/sign/debug/private.pem
cp .sign/certificate.pem watch/sign/debug/certificate.pem
cp .sign/private.pem watch/sign/release/private.pem
cp .sign/certificate.pem watch/sign/release/certificate.pem
chmod 600 .sign/private.pem watch/sign/debug/private.pem watch/sign/release/private.pem
