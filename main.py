import os
import json
import datetime
import argparse
import boto3
from pprint import pprint

def datetime_converter(object):
    """
    datetime_converter takes in the AWS datetime from the JSON array and converts it to a usable format in python.

    :param object: datetime object from AWS JSON response

    :return: returns the datetime object as a string
    """ 
    if isinstance(object, datetime.datetime):
        return object.__str__()

def extract_return_info(response):
    """
    extract_return_info takes in a response from modified launch template and returns the specific information needed.

    :param response: recieves a response from the modified_launch_template function

    :return: returns the launch template id, default version number, latest version number, and http status code
    """ 

    launch_template_id = response['LaunchTemplate']['LaunchTemplateId']
    default_version_number = response['LaunchTemplate']['DefaultVersionNumber']
    latest_version_number = response['LaunchTemplate']['LatestVersionNumber']
    http_status_code = response['ResponseMetadata']['HTTPStatusCode']

    return launch_template_id, default_version_number, latest_version_number, http_status_code

def get_all_mgn_launch_templates(region='us-east-2'):
    """
    get_all_mgn_launch_templates takes in a region and returns all the launch templates that are created by the AWS Application Migration Service except the default launch template that MGN uses as starter template.

    :param region: region to search for launch templates

    :return: returns a list of launch template ids
    """ 

    session = boto3.Session(region_name=region)
    ec2 = session.client('ec2')

    response = ec2.describe_launch_templates()

    launch_template_ids = []
    # check response and return the launch templates with a tag key of AWSApplicationMigrationServiceManaged and return only those LaunchTemplates
    for launch_template in response['LaunchTemplates']:
        for tag in launch_template['Tags']:
            if tag['Key'] == 'AWSApplicationMigrationServiceManaged' and launch_template['LaunchTemplateName'].startswith('created-and-used-by-application-migration-service-s'):
                launch_template_ids.append(launch_template['LaunchTemplateId'])

    return launch_template_ids

def get_launch_template(launch_template_id, region='us-east-2'):
    """
    get_launch_template takes in a launch template id and region and returns the launch template data.

    :param launch_template_id: mgn launch template id
    :param region: region to search for launch templates

    :return: returns the launch template data
    """ 

    session = boto3.Session(region_name=region)
    ec2 = session.client('ec2')

    response = ec2.describe_launch_template_versions(
        LaunchTemplateId=launch_template_id
    )

    return response['LaunchTemplateVersions'][0]

def modify_launch_template(launch_template_id, region, data):
    """
    modify_launch_template takes in a launch template id, region, and data and returns the launch template id, default version number, latest version number, and http status code.

    :param launch_template_id: mgn launch template id
    :param region: region to search for launch templates
    :param data: JSON data to modify the launch template
    
    :return: returns the launch template id, default version number, latest version number, and http status code
    """ 
    
    session = boto3.Session(region_name=region)
    ec2 = session.client('ec2')

    # Get the latest version of the launch template
    launch_templates = ec2.describe_launch_template_versions(
        LaunchTemplateId=launch_template_id
    )

    # Grab latest default version
    for launch_template in launch_templates['LaunchTemplateVersions']:
        if launch_template['DefaultVersion']:
            launch_template = launch_template
            break

    # Modify the necessary fields using original data and merge/overwrite with new data using merge method {**launch_template['LaunchTemplateData'],**data}
    modified_template_data = launch_template
    modified_template_data['LaunchTemplateData'] = {**launch_template['LaunchTemplateData'],**data}

    # Update the launch template
    modified_template = ec2.create_launch_template_version(
        LaunchTemplateId=launch_template_id,
        LaunchTemplateData=modified_template_data['LaunchTemplateData'],
        SourceVersion=str(launch_template['VersionNumber'])
    )

    # Set the new version as default
    response = ec2.modify_launch_template(
        LaunchTemplateId=launch_template_id,
        DefaultVersion=str(modified_template['LaunchTemplateVersion']['VersionNumber'])
    )

    # Return the launch template id, default version number, latest version number, and http status code
    return extract_return_info(response)

def write_dict_to_file(dict_data, filename):
    """
    write_dict_to_file takes in a dictionary and filename and writes the dictionary to a file.

    :param dict_data: dictionary data to write to file
    :param filename: name of the file

    :return: returns nothing
    """ 

    with open(filename, 'w') as f:
        json.dump(dict_data, f, default=datetime_converter, indent=4)

def write_original_data_to_file(launch_template_id, region):
    """
    write_original_data_to_file takes in a launch template id and region and writes the original data to a file.

    :param launch_template_id: mgn launch template id 
    :param region: region to search for launch templates

    :return: returns nothing
    """ 

    data = get_launch_template(launch_template_id=launch_template_id, region=region)
    tags = data['LaunchTemplateData']['TagSpecifications'][0]['Tags']
    for tag in tags:
        if tag['Key'] == 'Name':
            template_name = tag['Value']

    # Store the original data in a file for later use
    write_dict_to_file(data, f'Original/{template_name}.json')

def get_modified_data():
    """
    get_modified_data gets the modified data from the Modified folder and returns it as a dictionary.

    :return: returns the modified data as a dictionary
    """ 
    modified_data = {}
    template_data = {}
    for filename in os.listdir('Modified'):
        if filename.endswith('.json'):
            with open(f'Modified/{filename}', 'r') as f:
                template_data = json.load(f)
            modified_data[template_data['LaunchTemplateId']] = template_data
    return modified_data


def create_original_files(region):
    """
    create_original_files grabs the AWS launch template data and writes each launch template to a file in the Original folder.

    :return: returns nothing
    """ 

    # Get the original data from AWS
    original_data = get_all_mgn_launch_templates(region)

    for launch_template_id in original_data:
        # Get the launch template data
        data = get_launch_template(launch_template_id=launch_template_id, region=region)

        # Get the name of the launch template
        tags = data['LaunchTemplateData']['TagSpecifications'][0]['Tags']
        for tag in tags:
            if tag['Key'] == 'Name':
                template_name = tag['Value']

        # Store the original data in a file for later use
        write_dict_to_file(data, f'Original/{template_name}.json')

    print("To update the templates copy the Original file into the Modified folder and make the necessary changes.")

def deploy_modified_launch_templates(region):
    """
    deploy_modified_launch_templates grabs the modified launch template data from the files and looks at the launchtemplateid and deploys the launch templates in AWS.

    :return: returns nothing
    """ 
    
    # Get the original data from AWS
    original_data = get_all_mgn_launch_templates(region)

    # Get the modified data
    modified_data = get_modified_data()

    for launch_template_id in original_data:
        # Get the launch template data
        try:
            data = modified_data[launch_template_id]
        except KeyError:
            print(f'No modified data for {launch_template_id}')
            continue

        # Get the name of the launch template
        tags = data['LaunchTemplateData']['TagSpecifications'][0]['Tags']
        for tag in tags:
            if tag['Key'] == 'Name':
                template_name = tag['Value']

        # Update the launch template
        mod_launch = modify_launch_template(launch_template_id, region, data['LaunchTemplateData'])
        print(f'Updating {template_name}...TemplateID: {mod_launch[0]}, DefaultVersion: {mod_launch[1]}, LatestVersion: {mod_launch[2]}, HTTPStatusCode: {mod_launch[3]}')

# create cleanup function to delete the Original and Modified folders and files
def cleanup():
    """
    cleanup deletes the Original and Modified folders and files.

    :return: returns nothing
    """ 
    # delete Original and Modified folders and files
    if os.path.exists('Original'):
        for filename in os.listdir('Original'):
            os.remove(f'Original/{filename}')
        os.rmdir('Original')
    if os.path.exists('Modified'):
        for filename in os.listdir('Modified'):
            os.remove(f'Modified/{filename}')
        os.rmdir('Modified')

# Create Original and Modified folders if they don't exist
def create_folders():
    """
    create_folders creates the Original and Modified folders if they don't exist.

    :return: returns nothing
    """ 
    if not os.path.exists('Original'):
        os.makedirs('Original')
    if not os.path.exists('Modified'):
        os.makedirs('Modified')

help = """
This script will be used to easily manage MGN launch templates.  
It will allow you to create the original files, update the launch templates,
or cleanup the Original and Modified folders and files.
"""

parser = argparse.ArgumentParser(description=help)
parser.add_argument('--region', help='AWS region to search and modify launch templates for the default action')
subparsers = parser.add_subparsers(dest='command')

create_parser = subparsers.add_parser('create', help='Create original files')
create_parser.add_argument('region', help='AWS region to search and modify launch templates')

update_parser = subparsers.add_parser('update', help='Update launch templates')
update_parser.add_argument('region', help='AWS region to search and modify launch templates')

cleanup_parser = subparsers.add_parser('cleanup', help='Cleanup Original and Modified folders and files')

# Parse the arguments
args = parser.parse_args()

if args.command == 'create' and args.region:
    print("Creating original files...")
    create_folders()
    create_original_files(args.region)
elif args.command == 'update' and args.region:
    print("Updating launch templates...")
    create_folders()
    deploy_modified_launch_templates(args.region)
elif args.command == 'cleanup':
    print("Cleaning up Original and Modified folders and files...")
    cleanup()
elif args.command is None:
    print("No command provided. Running default action (create and update)...")
    if args.region:
        create_folders()
        create_original_files(args.region)
        deploy_modified_launch_templates(args.region)
    else:
        print("\nNOTICE!!!!\nNo region provided for the default action.\nNOTICE!!!!\n\n")
        parser.print_help()
else:
    parser.print_help()