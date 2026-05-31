# Terms: Podman, Docker, Container, Sandbox

This file exists because the CEO asked what "pod" means in the current testing
conversation.

## Container

A container is a temporary mini-computer environment for running a program with
its own filesystem view. It is useful for testing how a public package behaves
on a cleaner machine.

## Docker

Docker is the most common container tool. Many public projects say "run it in
Docker" when they mean "test it in a clean container."

## Podman

Podman is another container tool. It can run many Docker-style images and is
often easier to use rootlessly on Linux servers. In this project, Podman is only
a clean-environment test tool. It is not part of the package's required runtime.

## Sandbox

A sandbox is any restricted environment for running code. A container can be one
kind of sandbox, but the word can also mean a provider CLI's filesystem or tool
permission mode.

## Current Boundary

Do not log into providers inside a container now. Prepare input data only. The
desktop gate can later decide whether to use host logins, isolated container
logins, or manual/import mode.
