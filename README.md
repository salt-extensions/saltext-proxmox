# Salt Extension for Proxmox PVE

Salt Extension for interacting with Proxmox PVE

## Security

If you discover a security vulnerability, please refer
to [Salt's security guide][security].

## User Documentation

For setup and usage instructions, please refer to the
[User Documentation][docs].

## Contributing

The saltext-proxmox project welcomes contributions from anyone!

The [Salt Extensions guide][salt-extensions-guide] provides comprehensive instructions on all aspects
of Salt extension development, including [writing tests][writing-tests], [running tests][running-tests],
[writing documentation][writing-docs] and [rendering the docs][rendering-docs].

### Quickstart

To get started contributing, first clone this repository (or your fork):

```bash
# Clone the repo
git clone --origin upstream git@github.com:salt-extensions/saltext-proxmox.git

# Change to the repo dir
cd saltext-proxmox
```

#### Automatic
If you have installed [direnv][direnv], allowing the project's `.envrc` ensures
a proper development environment is present and the virtual environment is active.

Without `direnv`, you can still run the automation explicitly:

```bash
python3 tools/initialize.py
source .venv/bin/activate
```

#### Manual
Please follow the [first steps][first-steps], skipping the repository initialization and first commit.

### Pull request

Always make changes in a feature branch:

```bash
git switch -c my-feature-branch
```

To [submit a Pull Request][submitting-pr], you'll need a fork of this repository in
your own GitHub account. If you followed the instructions above,
set your fork as the `origin` remote now:

```bash
git remote add origin git@github.com:<your_fork>.git
```

Ensure you followed the [first steps][first-steps] and commit your changes, fixing any
failing `pre-commit` hooks. Then push the feature branch to your fork and submit a PR.

### Ways to contribute

Contributions come in many forms, and they’re all valuable! Here are some ways you can help
without writing code:

* **Documentation**: Especially examples showing how to use this project
  to solve specific problems.
* **Triaging issues**: Help manage [issues][issues] and participate in [discussions][discussions].
* **Reviewing [Pull Requests][PRs]**: We especially appreciate reviews using [Conventional Comments][comments].

You can also contribute by:

* Writing blog posts
* Sharing your experiences using Salt + Proxmox PVE
  on social media
* Giving talks at conferences
* Publishing videos
* Engaging in IRC, Discord or email groups

Any of these things are super valuable to our community, and we sincerely
appreciate every contribution!

[security]: https://github.com/saltstack/salt/blob/master/SECURITY.md
[salt-extensions-guide]: https://salt-extensions.github.io/salt-extension-copier/
[writing-tests]: https://salt-extensions.github.io/salt-extension-copier/topics/testing/writing.html
[running-tests]: https://salt-extensions.github.io/salt-extension-copier/topics/testing/running.html
[writing-docs]: https://salt-extensions.github.io/salt-extension-copier/topics/documenting/writing.html
[rendering-docs]: https://salt-extensions.github.io/salt-extension-copier/topics/documenting/building.html
[first-steps]: https://salt-extensions.github.io/salt-extension-copier/topics/creation.html#initialize-the-python-virtual-environment
[submitting-pr]: https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/proposing-changes-to-your-work-with-pull-requests/creating-a-pull-request-from-a-fork
[direnv]: https://direnv.net
[issues]: https://github.com/salt-extensions/saltext-proxmox/issues
[PRs]: https://github.com/salt-extensions/saltext-proxmox/pulls
[discussions]: https://github.com/salt-extensions/saltext-proxmox/discussions
[comments]: https://conventionalcomments.org/
[docs]: https://salt-extensions.github.io/saltext-proxmox/
