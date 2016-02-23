# Licensed under a 3-clause BSD style license - see LICENSE.rst
"""Model atmospheric emission and absorption for spectroscopic simulations.

The atmosphere model is responsible for calculating the spectral flux density
arriving at the telescope given a source flux entering the atmosphere. The
calculation is either performed as:

.. math::

    f(\lambda) = 10^{-e(\lambda) X / 2.5} s(\lambda) + a b(\lambda)

if ``extinct_emission`` is False, or else as:

.. math::

    f(\lambda) = 10^{-e(\lambda) X / 2.5} \left[
    s(\lambda) + a b(\lambda)\\right]

where :math:`s(\lambda)` is the source flux entering the atmosphere,
:math:`e(\lambda)` is the zenith extinction, :math:`X` is the airmass,
:math:`a` is the fiber entrance face area, and :math:`b(\lambda)` is the
sky emission surface brightness.

An atmosphere model is usually initialized from a configuration, for example:

    >>> import specsim.config
    >>> config = specsim.config.load_config('test')
    >>> atmosphere = initialize(config)
    >>> atmosphere.airmass
    1.0
"""
from __future__ import print_function, division

import numpy as np

import astropy.units as u

import speclite.filters


class Atmosphere(object):
    """Model atmospheric surface brightness and extinction.

    A simulation uses only our read-only :attr:`surface_brightness` and
    :attr:`extinction` attributes.  Use the :attr:`condition` and
    :attr:`airmass` attributes to update this model.  Refer to the
    :class:`moon model <Moon>` for details on updating the optional
    scattered moon model.

    Parameters
    ----------
    wavelength : astropy.units.Quantity
        Array of wavelengths with units where data is tabulated.
    surface_brightness_dict : dict
        Dictionary of tabulated sky emission surface brightness values. Each
        dictionary key defines a possible sky condition.
    extinction_coefficient : array
        Array of extinction coefficients tabulated on ``wavelength``.
    extinct_emission : bool
        If set, atmospheric extinction is applied to sky emission.
    condition : sky emission condition to use, which must be one of the keys
        of ``surface_brightness_dict``.
    airmass : float
        Airmass of the observation.
    moon : :class:`Moon` or None
        Model to use for scattered moonlight.
    """
    def __init__(self, wavelength, surface_brightness_dict,
                 extinction_coefficient, extinct_emission, condition, airmass,
                 moon):
        self._wavelength = wavelength
        self._surface_brightness_dict = surface_brightness_dict
        self._extinction_coefficient = extinction_coefficient
        self._extinct_emission = extinct_emission
        self._condition_names = surface_brightness_dict.keys()
        self._moon = moon
        self.condition = condition
        self.airmass = airmass


    @property
    def moon(self):
        """Moon or None: Model of scattered moonlight.

        See :class:`Moon` for details on changing scattered moon simulation
        parameters via this attribute.
        """
        return self._moon


    @property
    def surface_brightness(self):
        """astropy.units.Quantity: Total sky surface brightness.

        Includes both dark sky emission and (if configured) scattered moonlight.
        Changes to :attr:`condition` or :attr:`airmass` are reflected here.
        """
        sky = self._surface_brightness_dict[self.condition].copy()
        if self._extinct_emission:
            sky *= self.extinction
        if self.moon is not None and self.moon.visible:
            sky += self.moon.surface_brightness
        return sky


    @property
    def extinction(self):
        """numpy.ndarray: The extinction factor for the current model airmass.

        Tabulated as a function of wavelength. Changes to :attr:`airmass`
        automatically update these values.
        """
        return self._extinction


    @property
    def condition(self):
        """str: Sky emission condition.

        Must be one of the predefined names in :attr:`condition_names`.
        """
        return self._condition


    @condition.setter
    def condition(self, name):
        if name not in self._condition_names:
            raise ValueError(
                "Invalid condition '{0}'. Pick one of {1}."
                .format(name, self._condition_names))
        self._condition = name


    @property
    def condition_names(self):
        """list: The list of valid sky condition names.

        The valid names are keys of the ``atmosphere.sky.table.paths`` node,
        or "default" if only a single path is specified via a
        ``atmosphere.sky.table.path`` node.
        """
        return self._condition_names


    @property
    def airmass(self):
        """float: Observing airmass.
        """
        return self._airmass


    @airmass.setter
    def airmass(self, airmass):
        self._airmass = airmass
        self._extinction = 10 ** (-self._extinction_coefficient * airmass / 2.5)


    def plot(self):
        """Plot a summary of this atmosphere model.

        Requires that the matplotlib package is installed.
        """
        import matplotlib.pyplot as plt

        fig, ax1 = plt.subplots(figsize=(8, 4))
        ax1_rhs = ax1.twinx()

        wave = self._wavelength.to(u.Angstrom).value
        wave_unit = u.Angstrom

        sky_unit = 1e-17 * u.erg / (u.cm**2 * u.s * u.Angstrom * u.arcsec**2)
        sky = self.surface_brightness.to(sky_unit).value
        sky_min, sky_max = np.percentile(sky, (1, 99))

        ext = self._extinction_coefficient
        ext_min, ext_max = np.percentile(ext, (1, 99))

        ax1.scatter(wave, sky, color='g', lw=0, s=1.)
        if self.moon is not None and self.moon.visible:
            moon = self.moon.surface_brightness.to(sky_unit).value
            ax1.scatter(wave, moon, color='b', lw=0, s=1.)
            # Adjust the vertical limits to include the moon.
            moon_min, moon_max = np.percentile(moon, (1, 99))
            sky_min = min(moon_min, sky_min)
            sky_max = max(moon_max, sky_max)
        ax1_rhs.scatter(wave, ext, color='r', lw=0, s=1.)

        ax1.set_yscale('log')
        ax1_rhs.set_yscale('log')

        ax1.set_ylabel(
            'Surface Brightness [$10^{-17}\mathrm{erg}/(\mathrm{cm}^2' +
            '\mathrm{s} \AA)/\mathrm{arcsec}^2$]')
        ax1.set_ylim(0.5 * sky_min, 1.5 * sky_max)
        ax1_rhs.set_ylabel('Zenith Extinction')
        ax1_rhs.set_ylim(0.5 * ext_min, 1.5 * ext_max)

        ax1.set_xlabel('Wavelength [$\AA$]')
        ax1.set_xlim(wave[0], wave[-1])

        ncol = 2
        ax1.plot([], [], 'g-',
                 label='Sky ({0})'.format(self.condition))
        if self.moon is not None and self.moon.visible:
            ax1.plot([], [], 'b-', label='Moon')
            ncol += 1
        ax1.plot([], [], 'r-', label='Extinction')
        ax1.legend(bbox_to_anchor=(0., 1.02, 1., .102), loc=3,
                   ncol=ncol, mode='expand', borderaxespad=0.)


class Moon(object):
    """Model of scattered moonlight.

    Most of the work is performed by :func:`krisciunas_schaefer`, which
    implements the model of their 1991 paper. This class uses the predicted
    V-band surface brightness to normalize an input lunar spectrum (or solar
    spectrum if you assume the moon is grey).

    Use the :meth:`update` method to update scattered moon simulation
    parameters.

    This implementation is loosely based on and tested against [IDL code]
    (https://desi.lbl.gov/svn/code/desimodel/tags/0.4.2/pro/lunarmodel.pro) by
    Connie Rockosi.

    Parameters
    ----------
    wavelength : astropy.units.Quantity
        Array of wavelengths with units where data is tabulated.
    moon_spectrum : astropy.units.Quantity
        Tabulated spectrum of scattered moonlight with units of flux density.
        The normalization does not matter since it will be fixed by
        :meth:`get_lunar_surface_brightness`.  A solar spectrum can be used,
        which effectively assumes that the moon's reflectance is wavelength
        independent.
    extinction_coefficient : array
        Array of extinction coefficients tabulated on ``wavelength``.
    airmass : float
        Airmass of the observation.
    moon_zenith : astropy.units.Quantity
        See :func:`krisciunas_schaefer`.
    separation_angle : astropy.units.Quantity
        See :func:`krisciunas_schaefer`.
    moon_phase : float
        See :func:`krisciunas_schaefer`.
    """
    def __init__(self, wavelength, moon_spectrum, extinction_coefficient,
                 airmass, moon_zenith, separation_angle, moon_phase):
        self._wavelength = wavelength
        self._moon_spectrum = moon_spectrum
        self._extinction_coefficient = extinction_coefficient

        # Calculate the V-band extinction of the moon spectrum.
        self._vband = speclite.filters.load_filter('bessell-V')
        V = self._vband.get_ab_magnitude(moon_spectrum, wavelength)
        extinction = 10 ** (-extinction_coefficient / 2.5)
        Vstar = self._vband.get_ab_magnitude(
            moon_spectrum * extinction, wavelength)
        self._vband_extinction = Vstar - V

        # Update our observing parameters.
        self.update(airmass, moon_zenith, separation_angle, moon_phase)


    def update(self, airmass, moon_zenith, separation_angle, moon_phase):
        """Update the parameters of moon in this model.

        This method updates :attr:`surface_brightness`, which is the only
        output of this model used for simulation.

        Parameters
        ----------
        airmass : float
            Airmass of the observation.
        moon_zenith : astropy.units.Quantity
            See :func:`krisciunas_schaefer`.
        separation_angle : astropy.units.Quantity
            See :func:`krisciunas_schaefer`.
        moon_phase : float
            See :func:`krisciunas_schaefer`.
        """
        self._moon_phase = moon_phase
        self._moon_zenith = moon_zenith
        self._separation_angle = separation_angle

        if moon_zenith > 90 * u.deg:
            self._visible = False
            self._surface_brightness = (
                np.zeros_like(self._moon_spectrum) / (u.arcsec ** 2))
            return
        else:
            self._visible = True

        # Estimate the zenith angle corresponding to this observing airmass.
        # We invert eqn.3 of KS1991 for this (instead of eqn.14).
        self._obs_zenith = np.arcsin(
            np.sqrt((1 - airmass ** -2) / 0.96)) * u.rad

        # Calculate the V-band surface brightness of scattered moonlight.
        moon_V = krisciunas_schaefer(
            self.obs_zenith, moon_zenith, separation_angle,
            moon_phase, self.vband_extinction)

        # Calculate the wavelength-dependent extinction of moonlight
        # scattered once into the observed field of view.
        scattering_airmass = (1 - 0.96 * np.sin(moon_zenith) ** 2) ** (-0.5)
        extinction = (
            10 ** (-self._extinction_coefficient * scattering_airmass / 2.5) *
            (1 - 10 ** (-self._extinction_coefficient * airmass / 2.5)))
        self._surface_brightness = self._moon_spectrum * extinction

        # Renormalized the extincted spectrum to the correct V-band magnitude.
        raw_V = self._vband.get_ab_magnitude(
            self._surface_brightness, self._wavelength) * u.mag
        area = 1 * u.arcsec ** 2
        self._surface_brightness *= 10 ** (
            -(moon_V * area - raw_V) / (2.5 * u.mag)) / area


    @property
    def visible(self):
        """Is moon above the horizon?
        """
        return self._visible


    @property
    def surface_brightness(self):
        """Tabulated scattered moonlight surface brightness.

        This attribute is updated by :meth:`update`.
        """
        return self._surface_brightness

    @property
    def moon_phase(self):
        """Read-only value of the moon phase.

        Use :meth:`update` to update this value.
        """
        return self._moon_phase


    @property
    def obs_zenith(self):
        """Read-only value of the observing zenith angle.

        This attribute is calculated from the airmass passed to :meth:`update`
        by inverting Eqn.3 of Krisciunas & Schaefer 1991:

        .. math::

            X = (1 - 0.96 \sin^2 Z)^{-0.5}
        """
        return self._obs_zenith

    @property
    def moon_zenith(self):
        """Read-only value of the moon zenith angle.

        Use :meth:`update` to update this value.
        """
        return self._moon_zenith


    @property
    def separation_angle(self):
        """Read-only value of the observation-moon separation angle.

        Use :meth:`update` to update this value.
        """
        return self._separation_angle


    @property
    def vband_extinction(self):
        """Read-only value of the V-band extinction of the moon spectrum.

        Calculated as V* - V where V is the Bessell-V magnitude of the
        input lunar spectrum and V* is calculated with airmass 1.0
        extinction applied.
        """
        return self._vband_extinction


def krisciunas_schaefer(obs_zenith, moon_zenith, separation_angle, moon_phase,
                        vband_extinction):
    """Calculate the scattered moonlight surface brightness in V band.

    Based on Krisciunas and Schaefer, "A model of the brightness of moonlight",
    PASP, vol. 103, Sept. 1991, p. 1033-1039 (http://dx.doi.org/10.1086/132921).
    Equation numbers in the code comments refer to this paper.

    This method has several caveats but the authors find agreement with data at
    the 8% - 23% level.  See the paper for details.

    The function :func:`plot_lunar_brightness` provides a convenient way to
    plot this model's predictions as a function of observation pointing.

    Parameters
    ----------
    obs_zenith : astropy.units.Quantity
        Zenith angle of the observation in angular units.
    moon_zenith : astropy.units.Quantity
        Zenith angle of the moon in angular units.
    separation_angle : astropy.units.Quantity
        Opening angle between the observation and moon in angular units.
    moon_phase : float
        Phase of the moon from 0.0 (full) to 1.0 (new), which can be calculated
        as abs((d / D) - 1) where d is the time since the last new moon
        and D = 29.5 days is the period between new moons.  The corresponding
        illumination fraction is ``0.5*(1 + cos(pi * moon_phase))``.
    vband_extinction : float
        V-band extinction coefficient to use.

    Returns
    -------
    astropy.units.Quantity
        Observed V-band surface brightness of scattered moonlight.
    """
    moon_phase = np.asarray(moon_phase)
    if np.any((moon_phase < 0) | (moon_phase > 1)):
        raise ValueError(
            'Invalid moon phase {0}. Expected 0-1.'.format(moon_phase))
    # Calculate the V-band magnitude of the moon (eqn. 9).
    abs_alpha = 180. * moon_phase
    m = -12.73 + 0.026 * abs_alpha + 4e-9 * abs_alpha ** 4
    # Calculate the illuminance of the moon outside the atmosphere in
    # foot-candles (eqn. 8).
    Istar = 10 ** (-0.4 * (m + 16.57))
    # Calculate the scattering function (eqn.21).
    rho = separation_angle.to(u.deg).value
    f_scatter = (10 ** 5.36 * (1.06 + np.cos(separation_angle) ** 2) +
                 10 ** (6.15 - rho / 40.))
    # Calculate the scattering airmass along the lines of sight to the
    # observation and moon (eqn. 3).
    X_obs = (1 - 0.96 * np.sin(obs_zenith) ** 2) ** (-0.5)
    X_moon = (1 - 0.96 * np.sin(moon_zenith) ** 2) ** (-0.5)
    # Calculate the V-band moon surface brightness in nanoLamberts.
    B_moon = (f_scatter * Istar *
        10 ** (-0.4 * vband_extinction * X_moon) *
        (1 - 10 ** (-0.4 * (vband_extinction * X_obs))))
    # Convert from nanoLamberts to to mag / arcsec**2 using eqn.19 of
    # Garstang, "Model for Artificial Night-Sky Illumination",
    # PASP, vol. 98, Mar. 1986, p. 364 (http://dx.doi.org/10.1086/131768)
    return ((20.7233 - np.log(B_moon / 34.08)) / 0.92104 *
            u.mag / (u.arcsec ** 2))


def plot_lunar_brightness(moon_zenith, moon_azimuth, moon_phase,
                          vband_extinction=0.162, ngrid=250,
                          cmap='YlGnBu', figure_size=(8, 6)):
    """Create a polar plot of the scattered moon brightness in V band.

    Evaluates the model of :func:`krisciunas_schaefer` on a polar grid of
    observation pointings, for a fixed moon position and phase.

    This method requires that matplotlib is installed.

    Parameters
    ----------
    moon_zenith : astropy.units.Quantity
        See :func:`krisciunas_schaefer`.
    moon_azimuth : astropy.units.Quantity
        Aziumuthal angle of the moon in angular units.  Azimuth is measured
        clockwize from zero (North).
    moon_phase : float
        See :func:`krisciunas_schaefer`.
    vband_extinction : float
        See :func:`krisciunas_schaefer`.
    ngrid : int
        Size of observing location zenith and azimuth grids to use.
    cmap : str
        Name of the matplotlib color map to use.
    figure_size : tuple or None
        Tuple (width, height) giving the figure dimensions in inches.

    Returns
    -------
    tuple
        Tuple (fig, ax, cax) of matplotlib objects created for this plot. You
        can ignore these unless you want to make further changes to the plot.
    """
    import matplotlib.pyplot as plt

    # Build a grid in observation (zenith, azimuth).
    # Build a grid in observation (zenith, azimuth).
    obs_zenith = np.linspace(0., 90., ngrid, endpoint=False) * u.deg
    obs_az = (np.linspace(0., 360., ngrid) * u.deg)[:, np.newaxis]

    # Calculate the separation angles.
    cos_sep = (np.cos(moon_zenith) * np.cos(obs_zenith) +
               np.cos(moon_azimuth - obs_az) * np.sin(moon_zenith) *
               np.sin(obs_zenith))
    sep = np.arccos(cos_sep)

    # Calculate the V-band moon brightness.
    moon_V = krisciunas_schaefer(
        obs_zenith, moon_zenith, sep, moon_phase, vband_extinction)

    # Initialize the plot. We are borrowing from:
    # http://blog.rtwilson.com/producing-polar-contour-plots-with-matplotlib/
    fig, ax = plt.subplots(
        figsize=figure_size, subplot_kw=dict(projection='polar'))
    r, theta = np.meshgrid(
        obs_zenith.to(u.deg).value, obs_az.to(u.rad).value[:,0], copy=False)
    ax.set_theta_zero_location('N')
    ax.set_theta_direction(-1)
    ax.set_ylim(0., 90.)

    # Draw a polar contour plot.
    cax = ax.contourf(theta, r, moon_V.value, 50, cmap=cmap)
    fig.colorbar(cax).set_label('Scattered Moon V [mag/arcsec2]')

    # Draw a point indicating the moon position.
    plt.scatter(moon_azimuth.to(u.rad).value, moon_zenith.to(u.deg).value,
                s=150., marker='o', color='w', lw=0.5, edgecolor='k')

    # Add labels.
    xy, coords = (1., 0.), 'axes fraction'
    plt.annotate('$k_V$ = {0:.3f}'.format(vband_extinction),
                 xy, xy, coords, coords,
                 horizontalalignment='right', verticalalignment='top',
                 size='x-large', color='k')
    xy, coords = (0., 0.), 'axes fraction'
    plt.annotate('$\\phi$ = {0:.1f}%'.format(100. * moon_phase),
                 xy, xy, coords, coords,
                 horizontalalignment='left', verticalalignment='top',
                 size='x-large', color='k')

    plt.tight_layout()
    return fig, ax, cax


def initialize(config):
    """Initialize the atmosphere model from configuration parameters.

    After an atmosphere model has been initialized, further changes to the
    input configuration will no effect unless this method is called to
    initialize a new model. However, certain model attributes can be
    varied after a model is initialized.  See :class:`Atmosphere` and
    :class:`Moon` for details.

    Parameters
    ----------
    config : :class:`specsim.config.Configuration`
        The configuration parameters to use.

    Returns
    -------
    Atmosphere
        An initialized :class:`atmosphere model <Atmosphere>`, possibly
        containing a :class:`scattered moonlight model <Moon>`.
    """
    atm_config = config.atmosphere

    # Load tabulated data.
    surface_brightness_dict = config.load_table(
        atm_config.sky, 'surface_brightness', as_dict=True)
    extinction_coefficient = config.load_table(
        atm_config.extinction, 'extinction_coefficient')

    # Initialize an optional lunar scattering model.
    moon_config = getattr(atm_config, 'moon', None)
    if moon_config:
        moon_spectrum = config.load_table(moon_config, 'flux')
        c = config.get_constants(moon_config,
            ['moon_zenith', 'separation_angle', 'moon_phase'])
        moon = Moon(
            config.wavelength, moon_spectrum, extinction_coefficient,
            atm_config.airmass, c['moon_zenith'], c['separation_angle'],
            c['moon_phase'])
    else:
        moon = None

    atmosphere = Atmosphere(
        config.wavelength, surface_brightness_dict, extinction_coefficient,
        atm_config.extinct_emission, atm_config.sky.condition,
        atm_config.airmass, moon)

    if config.verbose:
        print(
            "Atmosphere initialized with condition '{0}' from {1}."
            .format(atmosphere.condition, atmosphere.condition_names))
        if moon:
            print(
                'Lunar V-band extinction coefficient is {0:.5f}.'
                .format(moon.vband_extinction))

    return atmosphere
