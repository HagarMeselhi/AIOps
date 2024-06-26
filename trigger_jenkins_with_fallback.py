import subprocess
import time
import requests
import xml.etree.ElementTree as ET

# Static variables
JENKINS_URL = "http://192.168.1.11:32000"  # Jenkins URL
JOB_NAME = "AIOps"  # Jenkins job name
USERNAME = "hagar"  # Jenkins username
API_TOKEN = "1101899da92bdcd7870d53060158610d0f"  # Jenkins API token
LOCAL_JENKINSFILE_PATH = "/Users/abdelaatyh2/downloads/pipelineFixed.groovy"  # Path to the local Jenkinsfile
BUILD_POLL_INTERVAL = 10  # Time in seconds between status checks

def get_jenkins_crumb(jenkins_url, username, api_token):
    try:
        result = subprocess.run(
            ['curl', '-s', '-u', f'{username}:{api_token}', f'{jenkins_url}/crumbIssuer/api/xml?xpath=concat(//crumbRequestField,":",//crumb)'],
            capture_output=True, text=True, check=True
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        print(f"Error obtaining Jenkins crumb: {e}")
        return None

def trigger_jenkins_build(jenkins_url, job_name, username, api_token):
    crumb = get_jenkins_crumb(jenkins_url, username, api_token)
    if crumb is None:
        print("Failed to obtain Jenkins crumb. Exiting.")
        return False

    try:
        result = subprocess.run(
            ['curl', '-X', 'POST', f'{jenkins_url}/job/{job_name}/build', '--user', f'{username}:{api_token}', '-H', crumb],
            capture_output=True, text=True, check=True
        )
        if result.returncode == 0:
            print("Build triggered successfully")
            return True
        else:
            print(f"Failed to trigger build: {result.stdout}, {result.stderr}")
            return False
    except subprocess.CalledProcessError as e:
        print(f"Error triggering Jenkins build: {e}")
        print("Response:", e.stdout)
        print("Error:", e.stderr)
        return False

def upload_and_trigger_local_jenkinsfile(jenkins_url, local_jenkinsfile_path, job_name, username, api_token):
    crumb = get_jenkins_crumb(jenkins_url, username, api_token)
    if crumb is None:
        print("Failed to obtain Jenkins crumb. Exiting.")
        return False

    try:
        with open(local_jenkinsfile_path, 'r') as f:
            jenkinsfile_content = f.read()

        config_xml = f"""
<flow-definition plugin="workflow-job@2.39">
  <description>Fallback job</description>
  <keepDependencies>false</keepDependencies>
  <properties/>
  <definition class="org.jenkinsci.plugins.workflow.cps.CpsFlowDefinition" plugin="workflow-cps@2.80">
    <script>{jenkinsfile_content}</script>
    <sandbox>true</sandbox>
  </definition>
  <triggers/>
  <disabled>false</disabled>
</flow-definition>
        """
        update_job_result = subprocess.run(
            ['curl', '-X', 'POST', f'{jenkins_url}/job/{job_name}/config.xml', '--user', f'{username}:{api_token}', '-H', crumb, '--data', config_xml, '-H', 'Content-Type:application/xml'],
            capture_output=True, text=True, check=True
        )
        if update_job_result.returncode == 0:
            print(f"Job {job_name} updated successfully with fallback Jenkinsfile")
        else:
            print(f"Failed to update job: {update_job_result.stdout}, {update_job_result.stderr}")
            return False

        # Trigger the updated job
        return trigger_jenkins_build(jenkins_url, job_name, username, api_token)
    except subprocess.CalledProcessError as e:
        print(f"Error uploading Jenkinsfile: {e}")
        print("Response:", e.stdout)
        print("Error:", e.stderr)
        return False

def get_last_build_number(jenkins_url, job_name, username, api_token):
    try:
        response = requests.get(f"{jenkins_url}/job/{job_name}/lastBuild/api/xml", auth=(username, api_token))
        if response.status_code == 200:
            root = ET.fromstring(response.text)
            build_number = root.find('number').text
            return int(build_number)
        else:
            print(f"Failed to get last build number: {response.status_code}, {response.text}")
            return None
    except requests.RequestException as e:
        print(f"Error getting last build number: {e}")
        return None

def get_build_status(jenkins_url, job_name, build_number, username, api_token):
    try:
        response = requests.get(f"{jenkins_url}/job/{job_name}/{build_number}/api/xml", auth=(username, api_token))
        if response.status_code == 200:
            root = ET.fromstring(response.text)
            status = root.find('result').text
            return status
        else:
            print(f"Failed to get build status: {response.status_code}, {response.text}")
            return None
    except requests.RequestException as e:
        print(f"Error getting build status: {e}")
        return None

def wait_for_build_to_finish(jenkins_url, job_name, build_number, username, api_token):
    while True:
        status = get_build_status(jenkins_url, job_name, build_number, username, api_token)
        if status:
            return status
        print(f"Build {build_number} is still running...")
        time.sleep(BUILD_POLL_INTERVAL)

def main():
    # Trigger the initial build
    success = trigger_jenkins_build(JENKINS_URL, JOB_NAME, USERNAME, API_TOKEN)
    if success:
        last_build_number = get_last_build_number(JENKINS_URL, JOB_NAME, USERNAME, API_TOKEN)
        if last_build_number:
            print(f"Waiting for build {last_build_number} to finish...")
            status = wait_for_build_to_finish(JENKINS_URL, JOB_NAME, last_build_number, USERNAME, API_TOKEN)
            print(f"Build {last_build_number} finished with status: {status}")
            if status != "SUCCESS":
                print(f"Initial build failed, updating job {JOB_NAME} with fallback Jenkinsfile from {LOCAL_JENKINSFILE_PATH}")
                if upload_and_trigger_local_jenkinsfile(JENKINS_URL, LOCAL_JENKINSFILE_PATH, JOB_NAME, USERNAME, API_TOKEN):
                    last_build_number = get_last_build_number(JENKINS_URL, JOB_NAME, USERNAME, API_TOKEN)
                    if last_build_number:
                        print(f"Waiting for fallback build {last_build_number} to finish...")
                        status = wait_for_build_to_finish(JENKINS_URL, JOB_NAME, last_build_number, USERNAME, API_TOKEN)
                        print(f"Fallback build {last_build_number} finished with status: {status}")
                    else:
                        print("Failed to get last build number for fallback build.")
                else:
                    print(f"Failed to trigger fallback job {JOB_NAME}.")
            else:
                print("Initial build succeeded.")
        else:
            print("Failed to get last build number for initial build.")
    else:
        print("Failed to trigger initial build.")

if __name__ == "__main__":
    main()
