terraform {
  # Configure this partial backend with an untracked backend.hcl before the
  # first adoption apply. Local state must not become the source of truth.
  backend "s3" {}
}
