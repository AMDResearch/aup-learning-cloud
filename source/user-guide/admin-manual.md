<!-- Copyright (C) 2025 Advanced Micro Devices, Inc. All rights reserved.  Portions of this notebook consist of AI-generated content. -->
<!--
Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
-->


# Admin Manual — JupyterHub Components and Workflows

This page describes advanced implementation details and workflows. For day-to-day configuration (auth, images, quotas, storage), use the [Configuration Reference](../jupyterhub/configuration-reference.md) and [Single-Node Deployment](../installation/single-node.md). Single-node deployments can use `sudo ./auplc-installer rt upgrade` from the repo root after editing `runtime/values.yaml`; multi-node or custom Helm deployments use `bash scripts/helm_upgrade.bash` from the `runtime/` directory.

## Multi-login Authenticator

```python

c.MultiAuthenticator.authenticators = [
    {
        "authenticator_class": CustomGitHubOAuthenticator,
        "url_prefix": "/github",
    },
    {
        "authenticator_class": SimpleGroupAuthenticator,
        "url_prefix": "/local",
    },
]
```
This is an example setting for multi-login. It uses `CustomGitHubOAuthenticator` for GitHub login and `SimpleGroupAuthenticator` for local login. The `url_prefix` is used to distinguish between the two login methods. And the callback URL is set to `/hub/<method>/oauth_login`.

To enable multi-login, we use `MultiAuthenticator` which should be manually added to Hub mirror using `RUN pip install jupyterhub-multiauthenticator`.

The display of multi-login method on each page are reloaded in `CustomMultiAuthenticator`. We can manually edit the login options for each login methods.
```python
class CustomMultiAuthenticator(MultiAuthenticator):
    def get_custom_html(self, base_url):

        html = []

        for authenticator in self._authenticators:
            name = getattr(authenticator, "service_name", "authenticator")
            login_service = getattr(authenticator, "login_service", name)
            url = authenticator.login_url(base_url)

            if name ==  LOCAL_ACCOUNT_PREFIX:
                # LOCALACCOUNT
                html.append(f"""
                <div class="login-option mb-6 bg-white rounded-xl shadow-lg p-6">
                <form action="{url}" method="post">
                    <input type="hidden" name="_xsrf" value="{{{{ xsrf }}}}" />
                    <div class="mb-4">
                    <input type="text" name="username" placeholder="Username"
                            class="block w-full px-4 py-2 border rounded-md shadow-sm focus:ring-2 focus:ring-blue-500"
                            required />
                    </div>
                    <div class="mb-4">
                    <input type="password" name="password" placeholder="Password"
                            class="block w-full px-4 py-2 border rounded-md shadow-sm focus:ring-2 focus:ring-blue-500"
                            required />
                    </div>
                    <button type="submit"
                            class="w-full py-2 px-4 bg-blue-600 hover:bg-blue-700 text-white font-medium rounded-md">
                    Use LocalAccount Login
                    </button>
                </form>
                </div>
                """)
            else:
                # OAuth Button
                html.append(f"""
                <div class="login-option mb-4">
                <a role="button" class="w-full inline-block text-center py-3 px-4 bg-gray-800 text-white
                                    rounded-md hover:bg-gray-900 font-medium"
                    href="{url}{{% if next is defined and next|length %}}?next={{{{next}}}}{{% endif %}}">
                    Use {login_service} Login
                </a>
                </div>
                """)

        return "\n".join(html)
```

For the specific settings for each login method, please refer to the corresponding authenticator class.

## RemoteLabSpawner

In this script, we allocate resources for each user based on their permissions, for example GitHub teams. From the resources we granted, we will generate a resource allocation webpage for them. According to the resource user chooses, we will change the spawn settings for each image. When the user click the `Start` button, it assign a timer to stop the user's session. The timer should be changed in the frontend, please locate `value="20"` for further changes.

# Workflow

This describes some workflows for AUP Learning Cloud.

## Workflow 1: Apply config changes

1. Edit `runtime/values.yaml`
2. From the `runtime/` directory, run `bash scripts/helm_upgrade.bash` and wait. You can check its status with the `k9s` command.

## Workflow 2: add a new resource image

1. Create a new folder under `dockerfiles`, for example `dockerfiles/NewImage`.
2. Create a new Dockerfile under `dockerfiles/NewImage`, for example `dockerfiles/NewImage/Dockerfile`.
3. Write a new Dockerfile, and prepare `build.sh` for the image. Suggested starter image is `rocm/pytorch:latest` (~60GB).
4. Before actually pushing to Docker Hub, we suggest you to build and test image locally. For example: remove the `start.sh` script and use `docker run` to test on your local machine.
5. Give the name and tag for the image in `build.sh`.
6. Run `build.sh` (or `./build.sh`) to build and push to ghcr. Make sure you do have the permission to push to ghcr.
7. Add the new image to `runtime/values.yaml` as prepuller.
8. Add the new image to `dockerfile/Hub/templates/resource_options_form.html` for front page settings.
9. Add the new image in `runtime/jupyterhub/files/hub/jupyterhub_config.py`. Include `RESOURCE_IMAGES`, `RESOURCE_REQUIREMENTS` and `TEAM_RESOURCE_MAPPING`.
10. From the `runtime/` directory, run `bash scripts/helm_upgrade.bash` and wait. For new images, it may take up 3 hours for prepuller depending on the cluster network. You can inspect the status by `k9s` command. If there is any node halt, you can manually delete to restart the prepuller pods. If there is still halts, you can `ssh` into the node and `sudo systemctl restart k3s-server` to restart the k3s server.
11. If it takes too long, and causing `pending-upgraded` failure. You should list out past versions of the image by `helm history jupyterhub -n jupyterhub` . Then you can rollback to a previous version by `helm rollback jupyterhub <version> -n jupyterhub`. After the rollback, run `bash scripts/helm_upgrade.bash` again from the `runtime/` directory.


## Workflow 3: Update an existing image

1. Edit the version settings in `build.sh`, `values.yaml` and `jupyterhub_config.py`.
2. Build and push to ghcr.
3. Run `scripts/helm_upgrade.bash` and wait.
If there is any problem, refer to `step10~11` in `Workflow 2`.

## Workflow 4: edit resource-limitation of an existing image (backend and frontend)
1. Edit `runtime/jupyterhub/files/hub/jupyterhub_config.py`. Especially `RESOURCE_REQUIREMENTS` and `TEAM_RESOURCE_MAPPING`.
2. If you hope to change user permissions for a image, you can edit `TEAM_RESOURCE_MAPPING`. For localAccount users, you can edit `RemoteLabKubeSpawner::get_user_teams`.
3. If you hope to change the information on the webpage, you can edit `resource_options_form.py::RESOURCE_SPECS`.
4. If you made changes to webpage, you should rebuild the hub image and push to ghcr. The update image version in `values.yaml`.
5. Run `scripts/helm_upgrade.bash` and wait.

## Workflow 5: change login settings (methods, account, password, localAccount...)

1. You can change the login method in `runtime/jupyterhub/files/hub/jupyterhub_config.py`, with `c.JupyterHub.authenticator_class = CustomMultiAuthenticator`.
2. To config GitHub OAuth, you should refer to this [post](https://jupyterhub.readthedocs.io/en/latest/howto/configuration/config-ghoauth.html). The main configs are in `runtime/values.yaml`.
3. To config localAccount, you should refer to `SimpleGroupAuthenticator`. The main configs are in `runtime/jupyterhub/files/hub/jupyterhub_config.py`. All users within one group shares the same password. 
4. To temporary ban login methods for testing cases, you can edit `runtime/jupyterhub/files/hub/jupyterhub_config.py`, to set`c.JupyterHub.authenticator_class = "dummy"`. Thus any passwd and username will be accepted.
5. Run `scripts/helm_upgrade.bash` and wait.

## Workflow 6: change announcement on login page

1. Change html lines in `runtime/values.yaml`.
2. Run `scripts/helm_upgrade.bash` and wait.
