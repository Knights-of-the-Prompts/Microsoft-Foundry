<div align="center">
    <img src="../../media/image-infra2.png" width="100%" alt="Microsoft Foundry">
</div>

# Cost Control for Hackathons

A unified PowerShell script for deploying cost control policies and budget alerts to Azure resource groups.

## Overview

The `SimplifiedCostControl.ps1` script provides complete cost protection:
1. **Deploys policies** that deny expensive resource deployments
2. **Creates budget alerts** at the resource group level with email notifications

## Protected Resources

The script automatically blocks deployment of expensive resources:
- **GPU instances**: `Standard_NC*`, `Standard_ND*`, `Standard_NV*`
- **High-memory VMs**: `Standard_M*`, `Standard_GS*`, `Standard_G*`
- **Premium storage**: `Premium_LRS`, `Premium_ZRS`, etc.
- **Premium App Services**: Premium and Isolated tiers
- **Premium databases**: SQL Premium and BusinessCritical tiers

## Budget Features

- Individual $500 budgets per resource group (configurable)
- Email alerts at 80% actual spend and 100% forecasted spend
- Monthly budget cycle with automatic renewal

## Quick Start

### Prerequisites
```powershell
# Install Azure PowerShell
Install-Module -Name Az -Force -Scope CurrentUser

# Authenticate with Azure
Connect-AzAccount

# Optional: Install Azure CLI for enhanced budget features
az login
```

### Basic Usage
```powershell
# Navigate to the policies directory
cd infra/policies

# Deploy policies and budgets
.\SimplifiedCostControl.ps1 -SubscriptionId "your-subscription-id" -ResourceGroupNames @("rg-team1", "rg-team2")

# Test first with dry run (recommended)
.\SimplifiedCostControl.ps1 -SubscriptionId "your-subscription-id" -ResourceGroupNames @("rg-team1") -DryRun
```

### With Email Notifications
```powershell
.\SimplifiedCostControl.ps1 `
    -SubscriptionId "your-subscription-id" `
    -ResourceGroupNames @("rg-team1", "rg-team2") `
    -BudgetAmount 750 `
    -NotificationEmails @("admin@example.com", "team@example.com")
```

## Parameters

| Parameter | Type | Required | Description | Default |
|-----------|------|----------|-------------|---------|
| `SubscriptionId` | String | Yes | Azure subscription ID | - |
| `ResourceGroupNames` | String[] | Yes | Array of resource group names | - |
| `BudgetAmount` | Integer | No | Budget amount per resource group (USD) | 500 |
| `NotificationEmails` | String[] | No | Email addresses for alerts | - |
| `DryRun` | Switch | No | Test mode without deployment | False |

## Required Permissions

- **Policy Contributor** role at the resource group level
- **Cost Management Contributor** role for budget creation

## What Happens

1. **Validation**: Checks authentication and resource groups
2. **Policy Deployment**: Creates and assigns cost control policies
3. **Budget Creation**: Sets up individual budgets with email alerts
4. **Confirmation**: Shows deployment summary

## Troubleshooting

### Common Issues

**Authentication Errors**
```powershell
# Check and re-authenticate
Get-AzContext
Connect-AzAccount
az account show
```

**Budget Creation Failed**
- Ensure Azure CLI is installed and authenticated
- Verify Cost Management permissions
- Check subscription supports budgets

**Permission Denied**
- Verify Policy Contributor role
- Ensure Cost Management Contributor role
- Check subscription access

## Recent Changes

**v1.2 (Oct 2025)**: Fixed email notifications and Azure CLI budget creation issues
**v1.1 (Oct 2025)**: Improved error handling and debugging
**v1.0 (Oct 2025)**: Initial release with unified cost control

---

**Perfect for hackathons, development environments, and any scenario where cost control is critical!**