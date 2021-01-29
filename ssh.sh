#!/bin/sh

#pushd ~/OnDemandMinecraft
ssh -i ondemandminecraft.pem ubuntu@$(cat serverip)
#popd
