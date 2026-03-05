<!-- Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved.  Portions of this notebook consist of AI-generated content. -->
<!--
Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
-->


# NFS Provisioner

## Install NFS Server
In kube-contorller node
```bash
sudo apt install nfs-kernel-server
```

## Create NFS Share
```bash
sudo mkdir -p /nfs
sudo chown -R nobody:nogroup /nfs
sudo chmod 777 /nfs
```

## Configure NFS Server
```bash
sudo nano /etc/exports
```

Add the following line:
```bash
/nfs <Your-Subnet-Addresses/24>(rw,sync,no_subtree_check,no_root_squash,insecure)
```

## Restart NFS Server
```bash
sudo systemctl restart nfs-kernel-server
```

## Install NFS Client
In all nodes (using ansible base role)
```bash
sudo apt install nfs-common
``` 

## Install NFS Provisioner

![NFS Provisioner](../../docs/images/nfs.jpg)

```bash
## Add repository
helm repo add nfs-subdir-external-provisioner https://kubernetes-sigs.github.io/nfs-subdir-external-provisioner/
helm repo update

helm install nfs-subdir-external-provisioner nfs-subdir-external-provisioner/nfs-subdir-external-provisioner \
    --namespace nfs-provisioner \
    --create-namespace \
    -f deploy/k8s/nfs-provisioner/values.yaml
```

## Set Default StorageClass

```bash
# Set nfs-client as the default StorageClass
kubectl patch storageclass nfs-client -p '{"metadata": {"annotations":{"storageclass.kubernetes.io/is-default-class":"true"}}}'

# Verify the default StorageClass
kubectl get storageclass
```
