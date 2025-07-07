#!/bin/bash

# Deploy HEIC2AVIF-PY to Kubernetes

echo "🚀 Deploying HEIC2AVIF-PY to Kubernetes..."

# Apply ConfigMap
echo "📋 Applying ConfigMap..."
kubectl apply -f heic2avif-py-configmap.yaml

# Apply Deployment and Service
echo "🛠️  Applying Deployment and Service..."
kubectl apply -f heic2avif-py-deployment.yaml

# Apply HPA
echo "📊 Applying Horizontal Pod Autoscaler..."
kubectl apply -f heic2avif-py-hpa.yaml

# Apply PDB
echo "🛡️  Applying Pod Disruption Budget..."
kubectl apply -f heic2avif-py-pdb.yaml

echo "✅ HEIC2AVIF-PY deployment complete!"

# Show deployment status
echo "📋 Deployment Status:"
kubectl get deployment heic2avif-py-deployment
kubectl get service heic2avif-py-service
kubectl get hpa heic2avif-py-hpa
kubectl get pdb heic2avif-py-pdb

echo ""
echo "🔍 Pod Status:"
kubectl get pods -l app=heic2avif-py

echo ""
echo "✅ HEIC2AVIF-PY is ready to receive requests from PhotoVault API"
