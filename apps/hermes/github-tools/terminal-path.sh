# Restore the Kubernetes client directory after Bash login startup files.
# LocalEnvironment invokes Bash as `bash -l -c`; image profiles can replace PATH.
case ":${PATH:-}:" in
  *:/opt/kubernetes-bin:*) ;;
  *) PATH="/opt/kubernetes-bin${PATH:+:${PATH}}" ;;
esac
export PATH
