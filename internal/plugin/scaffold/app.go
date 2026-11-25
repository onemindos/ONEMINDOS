// SPDX-License-Identifier: Apache-2.0

package scaffold

import "fmt"

func appFiles(manifest map[string]any, files map[string][]byte, id, template, image string) {
	meta := manifest["metadata"].(map[string]any)
	spec := manifest["spec"].(map[string]any)
	spec["runtime"] = "none"
	description := "Declarative settings app"
	instructions := "Edit the local settings schema to describe the controls the host renders."
	switch template {
	case "telemetry":
		description = "Telemetry event app"
		ext := spec["extensions"].(map[string]any)
		ext["events"] = map[string]any{"publish": []string{"reading"}}
		instructions = "The manifest declares an app-scoped reading event. Wire your data producer through the gateway event API. The starter requests no subscriptions and carries no credentials."
	case "container":
		description = "Container workload app"
		spec["runtime"] = "container"
		spec["manifests"] = "manifests"
		files["manifests/deployment.yaml"] = []byte(fmt.Sprintf(deployment, id, id, id, id, image))
		files["manifests/kustomization.yaml"] = []byte(kustomization)
		instructions = "Review the workload's user and resource requirements. The Deployment uses the supplied image pin and requests no host privileges."
	}
	meta["description"] = description
	files["README.md"] = []byte("# " + id + "\n\n" + instructions +
		"\n\nRun `onemind app check .` before sending the sources to the app gate. The starter is blocked until packaging, scans and review are complete.\n")
}

const deployment = `# SPDX-License-Identifier: Apache-2.0
apiVersion: apps/v1
kind: Deployment
metadata:
  name: %q
spec:
  replicas: 1
  selector:
    matchLabels:
      app.kubernetes.io/name: %q
  template:
    metadata:
      labels:
        app.kubernetes.io/name: %q
    spec:
      automountServiceAccountToken: false
      securityContext:
        runAsNonRoot: true
        seccompProfile:
          type: RuntimeDefault
      containers:
        - name: %q
          image: %q
          securityContext:
            allowPrivilegeEscalation: false
            capabilities:
              drop: [ALL]
          resources:
            requests:
              cpu: 100m
              memory: 64Mi
            limits:
              cpu: 500m
              memory: 128Mi
`

const kustomization = `# SPDX-License-Identifier: Apache-2.0
apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
resources: [deployment.yaml]
`
