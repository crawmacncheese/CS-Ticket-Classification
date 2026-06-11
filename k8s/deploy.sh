#!/usr/bin/env sh

K8S_DEPLOY_DIR="${K8S_ROOT_DIR}/${K8S_DIR}/deploy"

# Prepare and check k8s deploy directory.
if [ ! -d "$K8S_DEPLOY_DIR" ]; then
  echo "error: cluster directory for deployment '${K8S_DIR}' not exist for cluster '${K8S_API}'."
  exit 1;
fi

# Prepare holder directory for dynamic deployments.
rm -rf ${K8S_DEPLOY_DIR}/.generated && mkdir ${K8S_DEPLOY_DIR}/.generated

# Generate object configuration files for deployment.
for f in ${K8S_DEPLOY_DIR}/*.yaml
do
  envsubst < $f > "${K8S_DEPLOY_DIR}/.generated/$(basename $f)"
done

# Apply deployment.
kubectl apply -f ${K8S_DEPLOY_DIR}/.generated

# Watch deployment rollout.
for w in ${K8S_DEPLOY_DIR}/.generated/deploy*.yaml
do
  kubectl rollout status -f $w &
done
wait

