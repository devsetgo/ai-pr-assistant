FROM python:3.14-slim-bookworm

# There is deliberately no USER instruction. GitHub runs Docker container actions
# as root and needs that to write to GITHUB_WORKSPACE, so a non-root user would
# break the action. Static analysers flag the default root user; it does not
# apply to this kind of image.

RUN apt-get update \
    && apt-get install -y --no-install-recommends jq \
    && rm -rf /var/lib/apt/lists/*

COPY entrypoint.sh /action/entrypoint.sh
COPY autofill_description.py /action/autofill_description.py
COPY pr_description /action/pr_description
COPY requirements.lock /action/requirements.lock

# GitHub builds this image on every workflow run, so the install has to be
# reproducible: requirements.lock pins every package (direct and transitive) with
# hashes, and wheels-only means installing never runs a package's setup script.
# Regenerate the lock with `make lock` after changing requirements.txt.
RUN pip3 install --no-cache-dir --only-binary :all: --require-hashes -r /action/requirements.lock

ENTRYPOINT ["/action/entrypoint.sh"]
