#!/usr/bin/env python3

import os
import jinja2
from pathlib import Path  # python3 only
from dotenv import dotenv_values

tpl = r'''# THIS FILE IS AUTOGENERATED -- DO NOT EDIT #
#   Edit and Re-run .ci/gitlab/template.ci.py instead       #

stages:
  - sanity
  - test
  - build
  - install_checks
  - deploy

{% macro wheel_job_name(manylinux_version, pyver) -%}
wheel {{manylinux_version}} py {{pyver[0]}} {{pyver[2]}}
{%- endmacro -%}

{% macro never_on_schedule_rule(exclude_github=False) -%}
rules:
    - if: $CI_PIPELINE_SOURCE == "schedule"
      when: never
{%- if exclude_github %}
    - if: $CI_COMMIT_REF_NAME =~ /^github.*/
      when: never
{%- endif %}
    - when: on_success
{%- endmacro -%}

#************ definition of base jobs *********************************************************************************#

.test_base:
    retry:
        max: 2
        when:
            - runner_system_failure
            - stuck_or_timeout_failure
            - api_failure
    tags:
      - autoscaling
    rules:
        - if: $CI_COMMIT_REF_NAME =~ /^staging.*/
          when: never
        - when: on_success
    variables:
        PYPI_MIRROR_TAG: {{pypi_mirror_tag}}
        CI_IMAGE_TAG: {{ci_image_tag}}
        PYMOR_HYPOTHESIS_PROFILE: ci
        PYMOR_PYTEST_EXTRA: ""
        BINDERIMAGE: ${CI_REGISTRY_IMAGE}/binder:${CI_COMMIT_REF_SLUG}

.pytest:
    extends: .test_base
    tags:
      - long execution time
      - autoscaling
    environment:
        name: unsafe
    stage: test
    after_script:
      - .ci/gitlab/after_script.bash
    cache:
        key: same_db_on_all_runners
        paths:
          - .hypothesis
    artifacts:
        when: always
        name: "$CI_JOB_STAGE-$CI_COMMIT_REF_SLUG"
        expire_in: 3 months
        paths:
            - src/pymortests/testdata/check_results/*/*_changed
            - docs/source/*_extracted.py
            - coverage*
            - memory_usage.txt
            - .hypothesis
            - test_results*.xml

{# note: only Vanilla and numpy runs generate coverage or test_results so we can skip others entirely here #}
.submit:
    extends: .test_base
    image: {{registry}}/pymor/ci_sanity:{{ci_image_tag}}
    variables:
        XDG_CACHE_DIR: /tmp
    retry:
        max: 2
        when:
            - always
    environment:
        name: safe
    {{ never_on_schedule_rule(exclude_github=True) }}
    stage: deploy
    script: .ci/gitlab/submit.bash

.docker-in-docker:
    tags:
      - docker-in-docker
      - autoscaling
    extends: .test_base
    timeout: 45 minutes
    retry:
        max: 2
        when:
            - runner_system_failure
            - stuck_or_timeout_failure
            - api_failure
            - unknown_failure
            - job_execution_timeout
    {# this is intentionally NOT moving with CI_IMAGE_TAG #}
    image: {{registry}}/pymor/docker-in-docker:d1b5ebb4dc42a77cae82411da2e503a88bb8fb3a
    variables:
        DOCKER_HOST: tcp://docker:2375/
        DOCKER_DRIVER: overlay2
    before_script:
        - 'export SHARED_PATH="${CI_PROJECT_DIR}/shared"'
        - mkdir -p ${SHARED_PATH}
        - docker login -u $CI_REGISTRY_USER -p $CI_REGISTRY_PASSWORD $CI_REGISTRY
    services:
        - name: {{registry}}/docker:dind
          alias: docker
    environment:
        name: unsafe


# this should ensure binderhubs can still build a runnable image from our repo
.binder:
    extends: .docker-in-docker
    stage: install_checks
    needs: ["ci setup"]
    {{ never_on_schedule_rule() }}
    variables:
        USER: juno

.wheel:
    extends: .docker-in-docker
    stage: build
    needs: ["ci setup"]
    tags: [mike]
    {{ never_on_schedule_rule() }}


.check_wheel:
    extends: .test_base
    stage: install_checks
    {{ never_on_schedule_rule() }}
    services:
      - name: {{registry}}/pymor/devpi:1
        alias: pymor__devpi
    before_script:
      # bump to our minimal version
      - python3 -m pip install -U pip==19.0
      - python3 -m pip install devpi-client
      - devpi use http://pymor__devpi:3141/root/public --set-cfg
      - devpi login root --password none
      - devpi upload --from-dir --formats=* ./shared
    # the docker service adressing fails on other runners
    tags: [mike]

.sanity_checks:
    extends: .test_base
    image: {{registry}}/pymor/ci_sanity:{{ci_image_tag}}
    stage: sanity
#******** end definition of base jobs *********************************************************************************#

# https://docs.gitlab.com/ee/ci/yaml/README.html#workflowrules-templates
include:
  - template: 'Workflows/Branch-Pipelines.gitlab-ci.yml'

#******* sanity stage

# this step makes sure that on older python our install fails with
# a nice message ala "python too old" instead of "SyntaxError"
verify setup.py:
    extends: .sanity_checks
    script:
        - python3 setup.py egg_info

ci setup:
    extends: .sanity_checks
    script:
        - apk add jq
        - ${CI_PROJECT_DIR}/.ci/gitlab/ci_sanity_check.bash "{{ ' '.join(pythons) }}" "{{ ' '.join(manylinuxs) }}"

#****** test stage

{%- for script, py, para in matrix %}
{{script}} {{py[0]}} {{py[2]}}:
    extends: .pytest
    {{ never_on_schedule_rule() }}
    variables:
        COVERAGE_FILE: coverage_{{script}}__{{py}}
    services:
    {%- if script == "oldest" %}
        - name: {{registry}}/pymor/pypi-mirror_oldest_py{{py}}:{{pypi_mirror_tag}}
          alias: pypi_mirror
    {%- elif script in ["pip_installed", "numpy_git"] %}
        - name: {{registry}}/pymor/pypi-mirror_stable_py{{py}}:{{pypi_mirror_tag}}
          alias: pypi_mirror
    {%- endif %}
    image: {{registry}}/pymor/testing_py{{py}}:{{ci_image_tag}}
    script:
        - |
          if [[ "$CI_COMMIT_REF_NAME" == *"github/PR_"* ]]; then
            echo selecting hypothesis profile "ci_pr" for branch $CI_COMMIT_REF_NAME
            export PYMOR_HYPOTHESIS_PROFILE="ci_pr"
          else
            echo selecting hypothesis profile "ci" for branch $CI_COMMIT_REF_NAME
            export PYMOR_HYPOTHESIS_PROFILE="ci"
          fi
        - ./.ci/gitlab/test_{{script}}.bash
{%- endfor %}

# THIS FILE IS AUTOGENERATED -- DO NOT EDIT #
#   Edit and Re-run .ci/gitlab/template.ci.py instead       #

'''


tpl = jinja2.Template(tpl)
pythons = ['3.7', '3.8', '3.9']
oldest = [pythons[0]]
newest = [pythons[-1]]
test_scripts = [
    ("mpi", pythons, 1),
]
# these should be all instances in the federation
binder_urls = [f'https://{sub}.mybinder.org/build/gh/pymor/pymor' for sub in ('gke', 'ovh', 'gesis')]
testos = [('fedora', '3.9'), ('debian_buster', '3.7'), ('debian_bullseye', '3.9')]

env_path = Path(os.path.dirname(__file__)) / '..' / '..' / '.env'
env = dotenv_values(env_path)
ci_image_tag = env['CI_IMAGE_TAG']
pypi_mirror_tag = env['PYPI_MIRROR_TAG']
manylinuxs = ['2010', '2014']
registry = "zivgitlab.wwu.io/pymor/docker"
with open(os.path.join(os.path.dirname(__file__), 'ci.yml'), 'wt') as yml:
    matrix = [(sc, py, pa) for sc, pythons, pa in test_scripts for py in pythons]
    yml.write(tpl.render(**locals()))
