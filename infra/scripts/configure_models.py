#!/usr/bin/env python

import os
import rich_click as click
import yaml
from pathlib import Path
from dotenv import load_dotenv
import subprocess
from ai_config import *
from dotenv_azd import load_azd_env

load_azd_env()
load_dotenv(".env")
load_dotenv(".env.state")


def first(array):
    return next(iter(array), None)

def select_model(role, names, default = None):
    import survey
    default_index = names.index(default) if default and default in names else 0
    index = survey.routines.select(f"Pick a {click.style(role, bold=True)} deployment name: ", options = names, index = default_index)
    deployment=names[index]
    return deployment

def select_region(regions, default = None):
    import survey
    regions = list(regions)
    default_index = regions.index(default) if default and default in regions else 0
    index = survey.routines.select(f"Pick a region: ", options = regions, index = default_index)
    region=regions[index]
    return region

def decorators(decorators):
    def decorator(f):
        for d in reversed(decorators):
            f = d(f)
        return f
    return decorator

def role_option(ai_config, regions, role):
    return click.option(f'--{role}-deployment',
        type=click.Choice(get_deployment_names(ai_config=ai_config, regions=regions, role=role)),
        default=os.getenv(role_deployment_env_var_name(role)),
        help=f'The name of the {role} deployment to select.'
        )

def role_deployment_env_var_name(role):
    return f'{role.upper()}_DEPLOYMENT_NAME'

def role_model_env_var_name(role):
    return f'{role.upper()}_MODEL_NAME'

def role_model_api_env_var_name(role):
    return f'{role.upper()}_MODEL_API'

def azd_set_env(name, value):
    subprocess.run(['azd', 'env', 'set', name, value], shell=False, capture_output=True, text=True)

def bold(text):
    return click.style(text, bold=True)

if __name__ == '__main__':

    # Read ai.yaml, collect roles and build a CLI option for each deployment model role
    ai_config = read_ai_config()
    roles = get_roles(ai_config.data)
    regions = get_regions(ai_config.data)
    role_options = [role_option(ai_config.data, regions, role) for role in roles]

    @click.command()
    @decorators(role_options)
    @click.option('--set-azd-env/--no-set-azd-env', default=True, help='Set the selected deployment names as azd environment variables.')
    @click.option('--region', '-r', multiple=True, default=None, help='Restricts which regions to consider for models. Defaults to all regions.')
    def select_models(set_azd_env, region,  **kwargs):
        roles_str = ", ".join(map(lambda r: bold(r), roles))
        click.echo(f"Select which models to use for roles {roles_str}.")
        click.echo("Each selection narrows down future selections based on the region:")
        values = []
        selected_platforms = {}
        regions = get_regions(ai_config.data)
        if region:
            regions = regions & set(region)
        for arg_name, arg_value in kwargs.items():
            if not regions:
                raise Exception(f"No regions available. Check ai.yaml")
            role = arg_name.replace('_deployment', '')
            names = get_deployment_names(ai_config.data, regions, role, selected_platforms=selected_platforms)
            if not names:
                raise Exception(f"No {role} model could be found in regions {', '.join(regions)}. Check ai.yaml")
            arg_value = select_model(role, names, default = arg_value)
            descriptor = ai_config.descriptors[arg_value]
            regions = regions & descriptor.regions

            # Track selected platform for teacher/student roles
            platform = descriptor.data.get('platform')
            if platform and role in ['teacher', 'student']:
                selected_platforms[role] = platform

            values.append((role_deployment_env_var_name(role), arg_value))
            values.append((role_model_env_var_name(role), descriptor.model.name))
            values.append((role_model_api_env_var_name(role), descriptor.model.api))

        region = select_region(regions, os.getenv("AZURE_LOCATION"))
        values.append(("AZURE_LOCATION", region))

        if set_azd_env:
            click.echo()
            click.echo('Saving model selection to azd environment:')
            for name, value in values:
                click.echo(f' - {name}={value}')
                azd_set_env(name, value)

    select_models()
