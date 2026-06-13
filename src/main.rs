//! Generic industrial-protocol device simulator.
//!
//! One binary serves the same config-driven simulation over any registered
//! protocol (selected via the config `protocols` section). Protocol adapters are
//! compiled in here and registered with the [`SimRegistry`]; adding a protocol is
//! a one-line `register_*` call.

use sim_core::{
    bootstrap_config, build_simulation, detect_run_mode, parse_args, run, RunMode, SimRegistry,
};

#[cfg(windows)]
fn pause_on_fatal_error() {
    use std::io::{self, Write};
    let _ = writeln!(io::stderr(), "\nPress Enter to close this window...");
    let _ = io::stderr().flush();
    let mut line = String::new();
    let _ = io::stdin().read_line(&mut line);
}

#[cfg(not(windows))]
fn pause_on_fatal_error() {}

fn fatal(msg: impl AsRef<str>) -> ! {
    eprintln!("{}", msg.as_ref());
    pause_on_fatal_error();
    std::process::exit(1);
}

/// Build the protocol registry with every compiled-in simulator adapter.
fn build_registry() -> SimRegistry {
    let mut registry = SimRegistry::new();
    proto_bacnet::register_sim(&mut registry);
    proto_modbus::register_sim(&mut registry);
    proto_opcua::register_sim(&mut registry);
    registry
}

fn main() {
    let (no_tui_flag, config_path) = parse_args();
    let mode = detect_run_mode(no_tui_flag);

    if mode == RunMode::Headless {
        env_logger::init_from_env(env_logger::Env::default().default_filter_or("info"));
        log::info!("Starting simulator...");
    }

    let config = match bootstrap_config(&config_path) {
        Ok(config) => config,
        Err(e) => fatal(format!(
            "Failed to load config from {}: {e}",
            config_path.display()
        )),
    };

    let simulation = match build_simulation(&config) {
        Ok(simulation) => simulation,
        Err(e) => fatal(format!("Failed to build simulation: {e}")),
    };

    let registry = build_registry();

    if let Err(e) = run(mode, config_path, config, simulation, registry) {
        fatal(format!("Simulator error: {e}"));
    }
}
