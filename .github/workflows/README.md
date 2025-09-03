diff --git a//dev/null b/.github/workflows/README.md
index 0000000000000000000000000000000000000000..87522f1ec8c7b7ef38801a2dbd152f262862e255 100644
--- a//dev/null
+++ b/.github/workflows/README.md
@@ -0,0 +1,7 @@
+# CI/CD Workflows
+
+The GitHub Actions in this directory run Python-based autoposter scripts and do not rely on Node.js tooling.
+
+If a workflow later needs Node.js, reintroduce a `package.json` here with at least
+a `name`, `version`, and any required dependencies.
+
