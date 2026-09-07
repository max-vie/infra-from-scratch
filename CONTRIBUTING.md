# Contributing

This personal learning project welcomes focused fixes, tests, and documentation
improvements.

Keep each change limited to one component or one documentation concern. Open an
issue before adding a component, dependency, protocol feature, or shared
abstraction so the change can be discussed before implementation.

Use the standard library unless an architecture decision record justifies a
dependency. Match the existing language and test style, add tests for observable
behavior and failure paths, and keep protocol limits explicit.

Run the relevant component tests before opening a pull request. Run the
integration suite when a change affects more than one component:

```bash
python -m unittest discover -s integration-tests -v
```

In the pull request, describe the behavior or decision being changed and list
the validation commands and results. Include a request and response example
when it helps explain a protocol change.
