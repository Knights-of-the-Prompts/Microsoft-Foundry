#!/usr/bin/env python3
"""
Azure AI Foundry Environment Setup Script
Automatically retrieves configuration from Azure deployment and updates .env file
"""

import subprocess
import json
import sys
import os
import re
from pathlib import Path


class Colors:
    """Terminal colors for better UX"""
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'


def print_header(text):
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'='*60}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{text.center(60)}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{'='*60}{Colors.ENDC}\n")


def print_success(text):
    print(f"{Colors.OKGREEN}✓ {text}{Colors.ENDC}")


def print_error(text):
    print(f"{Colors.FAIL}✗ {text}{Colors.ENDC}")


def print_warning(text):
    print(f"{Colors.WARNING}⚠ {text}{Colors.ENDC}")


def print_info(text):
    print(f"{Colors.OKCYAN}ℹ {text}{Colors.ENDC}")


def run_az_command(command, check=True, timeout=30):
    """Execute Azure CLI command and return output"""
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            check=check,
            timeout=timeout
        )
        return result.stdout.strip(), result.returncode
    except subprocess.TimeoutExpired:
        print_warning(f"Command timed out after {timeout} seconds")
        return "", 1
    except subprocess.CalledProcessError as e:
        return e.stderr.strip(), e.returncode


def check_az_login():
    """Check if user is logged in to Azure CLI"""
    print_info("Controleren of Azure CLI is ingelogd...")
    output, returncode = run_az_command("az account show", check=False)
    
    if returncode != 0:
        print_error("Je bent niet ingelogd in Azure CLI!")
        print_info("Voer eerst 'az login' uit en probeer opnieuw.")
        sys.exit(1)
    
    print_success("Azure CLI login succesvol geverifieerd")
    return json.loads(output)


def confirm_subscription(account_info):
    """Show current subscription and ask for confirmation"""
    print_header("Subscription Verificatie")
    print(f"Huidige subscription:")
    print(f"  Naam: {Colors.BOLD}{account_info['name']}{Colors.ENDC}")
    print(f"  ID:   {Colors.BOLD}{account_info['id']}{Colors.ENDC}")
    
    while True:
        response = input(f"\n{Colors.OKCYAN}Is dit de juiste subscription? (ja/nee): {Colors.ENDC}").lower()
        if response in ['ja', 'j', 'yes', 'y']:
            print_success("Subscription bevestigd")
            return account_info['id']
        elif response in ['nee', 'n', 'no']:
            print_warning("Gebruik 'az account set --subscription <subscription-id>' om de juiste subscription te selecteren")
            sys.exit(0)
        else:
            print_warning("Voer 'ja' of 'nee' in")


def list_resource_groups():
    """List all resource groups and let user select one"""
    print_header("Resource Group Selectie")
    print_info("Resource groups ophalen...")
    
    output, returncode = run_az_command("az group list --query '[].{name:name, location:location}' -o json")
    
    if returncode != 0:
        print_error("Kon resource groups niet ophalen")
        sys.exit(1)
    
    resource_groups = json.loads(output)
    
    if not resource_groups:
        print_error("Geen resource groups gevonden")
        sys.exit(1)
    
    print(f"\n{Colors.BOLD}Beschikbare Resource Groups:{Colors.ENDC}")
    for idx, rg in enumerate(resource_groups, 1):
        print(f"  {idx}. {rg['name']} ({rg['location']})")
    
    while True:
        try:
            choice = input(f"\n{Colors.OKCYAN}Selecteer resource group (1-{len(resource_groups)}): {Colors.ENDC}")
            idx = int(choice) - 1
            if 0 <= idx < len(resource_groups):
                selected = resource_groups[idx]['name']
                print_success(f"Resource group '{selected}' geselecteerd")
                return selected
            else:
                print_warning(f"Kies een nummer tussen 1 en {len(resource_groups)}")
        except ValueError:
            print_warning("Voer een geldig nummer in")


def find_ai_foundry_resources(resource_group):
    """Find AI Foundry (Cognitive Services) resources in the resource group"""
    print_header("Resources Ophalen")
    print_info("AI Foundry resources zoeken...")
    
    # Find AI Foundry / Cognitive Services accounts
    output, returncode = run_az_command(
        f"az cognitiveservices account list -g {resource_group} "
        f"--query \"[?kind=='AIServices' || kind=='OpenAI'].{{name:name, kind:kind, endpoint:properties.endpoint, location:location}}\" -o json"
    )
    
    if returncode != 0:
        print_warning("Kon geen Cognitive Services resources vinden")
        return None
    
    resources = json.loads(output)
    
    if not resources:
        print_warning("Geen AI Foundry resources gevonden in deze resource group")
        return None
    
    print_success(f"Gevonden: {len(resources)} AI resource(s)")
    for res in resources:
        print(f"  - {res['name']} ({res['kind']}) @ {res['location']}")
    
    return resources


def find_ai_projects(resource_group, ai_foundry_name):
    """Find AI Foundry projects"""
    print_info("AI Foundry projecten zoeken...")
    
    # Try method 1: Using az resource to find MachineLearningServices workspaces
    output, returncode = run_az_command(
        f"az resource list -g {resource_group} "
        f"--resource-type Microsoft.MachineLearningServices/workspaces "
        f"--query \"[].{{name:name, id:id}}\" -o json",
        check=False,
        timeout=15
    )
    
    if returncode == 0 and output:
        workspaces = json.loads(output)
        if workspaces:
            # Get details for each workspace to check if it's a project
            projects = []
            for ws in workspaces:
                # Get workspace details
                detail_output, detail_code = run_az_command(
                    f"az resource show --ids {ws['id']} -o json",
                    check=False,
                    timeout=10
                )
                if detail_code == 0 and detail_output:
                    details = json.loads(detail_output)
                    # Check if it's a project (has kind=project or appropriate tags)
                    kind = details.get('kind', '')
                    tags = details.get('tags', {})
                    
                    if kind == 'project' or kind == 'Project' or tags.get('azureml.workspaceKind') == 'project':
                        # Try to get the discovery URL
                        properties = details.get('properties', {})
                        discovery_url = properties.get('discoveryUrl', '')
                        
                        projects.append({
                            'name': ws['name'],
                            'endpoint': discovery_url
                        })
            
            if projects:
                print_success(f"Gevonden: {len(projects)} AI project(en)")
                for proj in projects:
                    print(f"  - {proj['name']}")
                return projects
    
    # Try method 2: Using az ml if available
    check_output, check_code = run_az_command("az ml --help", check=False, timeout=5)
    
    if check_code == 0:
        # AI Projects are of type Microsoft.MachineLearningServices/workspaces with kind=project
        output, returncode = run_az_command(
            f"az ml workspace list -g {resource_group} "
            f"--query \"[?tags.azureml\\\\.workspaceKind=='project' || kind=='project'].{{name:name, endpoint:discovery_url}}\" -o json",
            check=False,
            timeout=15
        )
        
        if returncode == 0 and output:
            projects = json.loads(output)
            if projects:
                print_success(f"Gevonden: {len(projects)} AI project(en)")
                for proj in projects:
                    print(f"  - {proj['name']}")
                return projects
    
    print_warning("Geen AI projecten gevonden")
    return None


def get_deployment_models(resource_group, ai_foundry_name):
    """Get deployed models from AI Foundry resource"""
    print_info("Model deployments ophalen...")
    
    output, returncode = run_az_command(
        f"az cognitiveservices account deployment list -g {resource_group} -n {ai_foundry_name} "
        f"--query '[].{{name:name, model:properties.model.name, version:properties.model.version}}' -o json",
        check=False
    )
    
    if returncode != 0:
        print_warning("Kon model deployments niet ophalen")
        return []
    
    deployments = json.loads(output) if output else []
    
    if deployments:
        print_success(f"Gevonden: {len(deployments)} model deployment(s)")
        for dep in deployments:
            print(f"  - {dep['name']} (model: {dep['model']})")
    else:
        print_warning("Geen model deployments gevonden")
    
    return deployments


def get_openai_key(resource_group, ai_foundry_name):
    """Get API key for AI Foundry resource"""
    print_info("API key ophalen...")
    
    output, returncode = run_az_command(
        f"az cognitiveservices account keys list -g {resource_group} -n {ai_foundry_name} "
        f"--query 'key1' -o tsv",
        check=False
    )
    
    if returncode == 0 and output:
        print_success("API key opgehaald")
        return output
    else:
        print_warning("Kon API key niet ophalen")
        return None


def update_env_file(config):
    """Update .env file with retrieved configuration"""
    print_header("Environment File Bijwerken")
    
    env_path = Path(__file__).parent / '.env'
    
    if not env_path.exists():
        print_error(f".env file niet gevonden op {env_path}")
        sys.exit(1)
    
    print_info(f"Laden van {env_path}")
    
    # Read current .env content
    with open(env_path, 'r') as f:
        content = f.read()
    
    # Update values
    replacements = {
        r'AZURE_SUBSCRIPTION_ID=.*': f'AZURE_SUBSCRIPTION_ID={config["subscription_id"]}',
        r'AZURE_RESOURCE_GROUP_NAME=.*': f'AZURE_RESOURCE_GROUP_NAME={config["resource_group"]}',
        r'AZURE_PROJECT_NAME=.*': f'AZURE_PROJECT_NAME={config["project_name"]} # the name of your Azure AI Foundry project',
        r'PROJECT_ENDPOINT=.*': f'PROJECT_ENDPOINT={config["project_endpoint"]} # the endpoint of your Azure AI Foundry project, you can find it in the Azure portal',
    }
    
    # Add agent model deployment if available
    if config.get("agent_model_deployment"):
        replacements[r'AGENT_MODEL_DEPLOYMENT_NAME=.*'] = f'AGENT_MODEL_DEPLOYMENT_NAME={config["agent_model_deployment"]} # or your custom GPT-4o deployment name. Make sure to change this to GPT-4o when using Deep Research tool because GPT-4.1 is not supported'
    
    # Add optional AZURE_OPENAI settings if available
    if config.get("azure_openai_endpoint"):
        # Uncomment and set AZURE_OPENAI_ENDPOINT
        content = re.sub(
            r'# AZURE_OPENAI_ENDPOINT=.*',
            f'AZURE_OPENAI_ENDPOINT={config["azure_openai_endpoint"]} # the endpoint of your Azure OpenAI resource, you can find it in the Azure portal',
            content
        )
    
    if config.get("azure_openai_api_key"):
        # Uncomment and set AZURE_OPENAI_API_KEY_NAME
        content = re.sub(
            r'# AZURE_OPENAI_API_KEY_NAME=.*',
            f'AZURE_OPENAI_API_KEY_NAME=api-key # the name of the API key for your Azure OpenAI resource',
            content
        )
    
    # Apply replacements
    for pattern, replacement in replacements.items():
        content = re.sub(pattern, replacement, content)
    
    # Write updated content
    with open(env_path, 'w') as f:
        f.write(content)
    
    print_success(f".env file succesvol bijgewerkt!")
    
    # Show what was configured
    print(f"\n{Colors.BOLD}Geconfigureerde waarden:{Colors.ENDC}")
    for key in ["subscription_id", "resource_group", "project_name", "agent_model_deployment"]:
        if config.get(key):
            print(f"  ✓ {key}: {config[key]}")


def main():
    """Main execution flow"""
    print_header("Azure AI Foundry Environment Setup")
    
    # Step 1: Check Azure CLI login
    account_info = check_az_login()
    
    # Step 2: Confirm subscription
    subscription_id = confirm_subscription(account_info)
    
    # Step 3: Select resource group
    resource_group = list_resource_groups()
    
    # Step 4: Find AI Foundry resources
    ai_resources = find_ai_foundry_resources(resource_group)
    
    if not ai_resources:
        print_error("Geen AI Foundry resources gevonden om te configureren")
        sys.exit(1)
    
    # Select first AI Foundry resource (or let user choose if multiple)
    ai_foundry = ai_resources[0]
    if len(ai_resources) > 1:
        print(f"\n{Colors.WARNING}Meerdere AI resources gevonden. Eerste wordt gebruikt: {ai_foundry['name']}{Colors.ENDC}")
    
    ai_foundry_name = ai_foundry['name']
    ai_foundry_endpoint = ai_foundry.get('endpoint', '')
    
    # Step 5: Find AI Projects
    projects = find_ai_projects(resource_group, ai_foundry_name)
    
    project_name = ""
    project_endpoint = ""
    
    if projects and len(projects) > 0:
        project = projects[0]
        project_name = project['name']
        project_endpoint = project.get('endpoint', '')
        
        # Try to construct the project endpoint if not available
        if not project_endpoint and ai_foundry_endpoint:
            # Extract foundry resource name from endpoint
            match = re.search(r'https://([^.]+)\.', ai_foundry_endpoint)
            if match:
                foundry_resource = match.group(1)
                project_endpoint = f"https://{foundry_resource}.services.ai.azure.com/api/projects/{project_name}"
    else:
        print_warning("Geen project gevonden, gebruik AI Foundry resource naam als fallback")
        project_name = ai_foundry_name
        if ai_foundry_endpoint:
            match = re.search(r'https://([^.]+)\.', ai_foundry_endpoint)
            if match:
                foundry_resource = match.group(1)
                project_endpoint = f"https://{foundry_resource}.services.ai.azure.com/api/projects/{project_name}"
    
    # Step 6: Get model deployments
    deployments = get_deployment_models(resource_group, ai_foundry_name)
    
    # Find GPT model deployment (prefer gpt-4o, gpt-4, or any gpt model)
    agent_model = None
    for dep in deployments:
        model_name = dep['model'].lower()
        if 'gpt-4o' in model_name:
            agent_model = dep['name']
            break
        elif 'gpt-4' in model_name and not agent_model:
            agent_model = dep['name']
        elif 'gpt' in model_name and not agent_model:
            agent_model = dep['name']
    
    if not agent_model and deployments:
        # Use first deployment as fallback
        agent_model = deployments[0]['name']
        print_warning(f"Geen GPT model gevonden, gebruik eerste deployment: {agent_model}")
    
    # Step 7: Get API key (optional for some setups)
    api_key = get_openai_key(resource_group, ai_foundry_name)
    
    # Step 8: Build configuration
    config = {
        "subscription_id": subscription_id,
        "resource_group": resource_group,
        "project_name": project_name,
        "project_endpoint": project_endpoint,
        "agent_model_deployment": agent_model,
        "azure_openai_endpoint": ai_foundry_endpoint,
        "azure_openai_api_key": api_key if api_key else None
    }
    
    # Step 9: Update .env file
    update_env_file(config)
    
    print_header("Setup Voltooid")
    print_success("Je kunt nu de workshop starten met de geconfigureerde environment!")
    print_info("Controleer het .env bestand voor de volledige configuratie")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n\n{Colors.WARNING}Setup geannuleerd door gebruiker{Colors.ENDC}")
        sys.exit(0)
    except Exception as e:
        print_error(f"Onverwachte fout: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
