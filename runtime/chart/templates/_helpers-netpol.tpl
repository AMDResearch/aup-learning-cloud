{{/*
Modifications Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved.
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
*/}}

{{- /*
  This named template renders egress rules for NetworkPolicy resources based on
  common configuration.

  It is rendering based on the `egressAllowRules` and `egress` keys of the
  passed networkPolicy config object. Each flag set to true under
  `egressAllowRules` is rendered to a egress rule that next to any custom user
  defined rules from the `egress` config.

  This named template needs to render based on a specific networkPolicy
  resource, but also needs access to the root context. Due to that, it
  accepts a list as its scope, where the first element is supposed to be the
  root context and the second element is supposed to be the networkPolicy
  configuration object.

  As an example, this is how you would render this named template from a
  NetworkPolicy resource under its egress:

    egress:
      # other rules here...

      {{- with (include "jupyterhub.networkPolicy.renderEgressRules" (list . .Values.hub.networkPolicy)) }}
      {{- . | nindent 4 }}
      {{- end }}

  Note that the reference to privateIPs and nonPrivateIPs relate to
  https://en.wikipedia.org/wiki/Private_network#Private_IPv4_addresses.
*/}}

{{- define "jupyterhub.networkPolicy.renderEgressRules" -}}
{{- $root := index . 0 }}
{{- $netpol := index . 1 }}
{{- if or (or $netpol.egressAllowRules.dnsPortsCloudMetadataServer $netpol.egressAllowRules.dnsPortsKubeSystemNamespace) $netpol.egressAllowRules.dnsPortsPrivateIPs }}
- ports:
    - port: 53
      protocol: UDP
    - port: 53
      protocol: TCP
  to:
  {{- if $netpol.egressAllowRules.dnsPortsCloudMetadataServer }}
    # Allow outbound connections to DNS ports on the cloud metadata server
    - ipBlock:
        cidr: {{ $root.Values.singleuser.cloudMetadata.ip }}/32
  {{- end }}
  {{- if $netpol.egressAllowRules.dnsPortsKubeSystemNamespace }}
    # Allow outbound connections to DNS ports on pods in the kube-system
    # namespace
    - namespaceSelector:
        matchLabels:
          kubernetes.io/metadata.name: kube-system
  {{- end }}
  {{- if $netpol.egressAllowRules.dnsPortsPrivateIPs }}
    # Allow outbound connections to DNS ports on destinations in the private IP
    # ranges
    - ipBlock:
        cidr: 10.0.0.0/8
    - ipBlock:
        cidr: 172.16.0.0/12
    - ipBlock:
        cidr: 192.168.0.0/16
  {{- end }}
{{- end }}

{{- if $netpol.egressAllowRules.nonPrivateIPs }}
# Allow outbound connections to non-private IP ranges
- to:
    - ipBlock:
        cidr: 0.0.0.0/0
        except:
          # As part of this rule:
          # - don't allow outbound connections to private IPs
          - 10.0.0.0/8
          - 172.16.0.0/12
          - 192.168.0.0/16
          # - don't allow outbound connections to the cloud metadata server
          - {{ $root.Values.singleuser.cloudMetadata.ip }}/32
{{- end }}

{{- if $netpol.egressAllowRules.privateIPs }}
# Allow outbound connections to private IP ranges
- to:
    - ipBlock:
        cidr: 10.0.0.0/8
    - ipBlock:
        cidr: 172.16.0.0/12
    - ipBlock:
        cidr: 192.168.0.0/16
{{- end }}

{{- if $netpol.egressAllowRules.cloudMetadataServer }}
# Allow outbound connections to the cloud metadata server
- to:
    - ipBlock:
        cidr: {{ $root.Values.singleuser.cloudMetadata.ip }}/32
{{- end }}

{{- with $netpol.egress }}
# Allow outbound connections based on user specified rules
{{ . | toYaml }}
{{- end }}
{{- end }}
