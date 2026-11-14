const babel = require('./babel.config');
module.exports = {
  plugins: {
    '@stylexjs/postcss-plugin': {
      include: ['src/**/*.{js,jsx,ts,tsx}'],
      babelConfig: {
        babelrc: false,
        parserOpts: { plugins: ['typescript', 'jsx'] },
        plugins: babel.plugins,
      },
      useCSSLayers: { before: ['reset', 'astryx-base', 'astryx-theme', 'ontara'] },
    },
  },
};
